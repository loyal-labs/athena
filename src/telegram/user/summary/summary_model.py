from collections import defaultdict
from logging import getLogger
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from src.shared.base_llm import VertexLLM
from src.telegram.user.summary.summary_schemas import ChatMessage

logger = getLogger("telegram.user.summary.summary_model")


class CommunityMessageProcessor:
    MIN_CLUSTER_SIZE = 2
    MIN_SAMPLES = 2
    CLUSTER_SELECTION_EPSILON = 0.7
    CLUSTER_SELECTION_METHOD = "leaf"
    INITIAL_ENGAGEMENT_THRESHOLD = 0.75
    MIN_MESSAGE_PERCENTAGE = 0.1
    MAX_MESSAGES = 1000
    STOP_WORDS = "english"
    NGRAM_RANGE = (1, 2)
    MIN_DF = 0.0
    MAX_DF = 1.0
    MAX_FEATURES = 1000

    def __init__(self, model: VertexLLM):
        self.model = model

        self.tfidf = TfidfVectorizer(
            stop_words=self.STOP_WORDS,
            ngram_range=self.NGRAM_RANGE,
            min_df=self.MIN_DF,
            max_df=self.MAX_DF,
        )

    async def analyze_messages(
        self, messages: list[ChatMessage], batch_size: int = 20
    ) -> tuple[list[ChatMessage], np.ndarray[Any, Any]]:
        # --- 1. Initial Filtering (Engagement Only) ---
        important_msgs = [
            msg
            for msg in messages
            if msg.engagement_score > self.INITIAL_ENGAGEMENT_THRESHOLD
        ]

        # Fallback: Ensure we have a minimum number of messages
        if len(important_msgs) < len(messages) * self.MIN_MESSAGE_PERCENTAGE:
            # Sort by engagement and take top N (percentage or MAX_MESSAGES)
            important_msgs = sorted(
                messages, key=lambda msg: msg.engagement_score, reverse=True
            )[
                : max(
                    int(len(messages) * self.MIN_MESSAGE_PERCENTAGE), self.MAX_MESSAGES
                )
            ]
        # --- 2. TF-IDF Calculation (on Filtered Messages) ---
        if not important_msgs:  # Handle the case where no messages pass the filter
            return [], np.array([])

        texts = [msg.message for msg in important_msgs]
        tfidf_matrix = self.tfidf.fit_transform(texts)  # type: ignore
        importance_scores = tfidf_matrix.sum(axis=1).A1  # type: ignore

        # --- 3. Get Embeddings ---
        embeddings = await self.get_model_embeddings(important_msgs)

        # Store importance scores *with* the messages for later use.
        important_msgs_with_scores = list(  # type: ignore
            zip(important_msgs, importance_scores, strict=True)  # type: ignore
        )
        return (important_msgs_with_scores, embeddings)  # type: ignore

    async def get_model_embeddings(
        self, messages: list[ChatMessage], batch_size: int = 250
    ) -> np.ndarray[Any, Any]:
        from sklearn.preprocessing import StandardScaler

        text_embeddings: list[np.ndarray[Any, Any]] = []
        time_features: list[int] = []

        # Process in batches to respect API limits
        for i in range(0, len(messages), batch_size):
            embedding_attempts = 0

            batch = messages[i : i + batch_size]

            batch_texts: list[str] = []
            batch_timestamps: list[int] = []

            for msg in batch:
                message = msg.message
                if msg.link_preview_title:
                    message += f"\n{msg.link_preview_title}"
                if msg.link_preview_description:
                    message += f"\n{msg.link_preview_description}"

                if message:  # Filter out empty messages
                    batch_texts.append(message)
                    batch_timestamps.append(int(msg.timestamp.timestamp()))

            if not batch_texts:
                continue

            time_features.extend(batch_timestamps)

            # Get embeddings from Gemini
            try:
                response = await self.model.embed_content(batch_texts, "CLUSTERING")
            except Exception as e:
                embedding_attempts += 1
                logger.error(f"Error embedding content: {e}")
                raise e

            text_embeddings.extend(response)  # type: ignore

        # Handle case where all messages were filtered out
        if not text_embeddings:
            return np.array([])

        # Normalize time features
        normalized_time_features = np.array(time_features).reshape(-1, 1)
        time_scaler = StandardScaler()
        normalized_time = time_scaler.fit_transform(normalized_time_features)  # type: ignore

        combined_embeddings = np.hstack([text_embeddings, normalized_time])  # type: ignore

        return np.array(combined_embeddings)

    async def cluster_messages(
        self,
        messages_with_scores: list[tuple[ChatMessage, float]],
        embeddings: np.ndarray[Any, Any],
    ) -> list[list[ChatMessage]]:
        from sklearn.cluster import HDBSCAN  # type: ignore
        from sklearn.preprocessing import StandardScaler

        messages, importance_scores = zip(*messages_with_scores, strict=True)  # Unpack
        messages, importance_scores = (
            list(messages),
            list(importance_scores),
        )  # Convert to list

        if not embeddings.size:  # Handle empty embeddings array
            return []

        scaler = StandardScaler()
        scaled_embeddings = scaler.fit_transform(embeddings)  # type: ignore

        clusterer = HDBSCAN(  # type: ignore
            min_cluster_size=self.MIN_CLUSTER_SIZE,
            min_samples=self.MIN_SAMPLES,
            cluster_selection_epsilon=self.CLUSTER_SELECTION_EPSILON,
            cluster_selection_method=self.CLUSTER_SELECTION_METHOD,
        ).fit(scaled_embeddings)  # type: ignore

        clusters: defaultdict[int, list[tuple[ChatMessage, float]]] = defaultdict(list)  # type: ignore
        # --- NOISE HANDLING: Discard Noise Messages ---
        for i, label in enumerate(clusterer.labels_):  # type: ignore
            if label != -1:  # Only process non-noise messages
                clusters[label].append((messages[i], importance_scores[i]))

        # --- Representative Message Selection (Highest Importance Score) ---
        representative_clusters: list[list[ChatMessage]] = []
        for _, msg_score_pairs in clusters.items():
            # Sort by importance score (descending) and take the top 2
            sorted_msgs = sorted(msg_score_pairs, key=lambda x: x[1], reverse=True)
            representative_clusters.append(
                [msg for msg, _ in sorted_msgs[:2]]
            )  # Keep top 2

        return representative_clusters
