# How to run
## 1. Running Locally
 - Use `uv`
 - Use Pylance in `strict` type checking mode
 - Each slice must be independent and decoupled, use `core/event_bus.py` to communicate. 
 - Use `commitizen` for commits

### 1.1 Start Server
1. Install `uv` package manager [from here](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer).
2. Install Python 3.12 if you don't have it.
```
uv python install 3.12
```
3. Activate virtual environment
```
source .venv/bin/activate
```
4. Create .env file from .env.example and fill out the data.

### 1.2 Manage Dependencies
1. Adding a dependency
```
uv add httpx
```
2. Removing a dependency
```python
uv remove httpx
```
3. Locking depencendies
```
uv lock
```

### 1.3 Manage Versions
- Use `cz commit` after adding changed files w/ `github add .`
- Use `git push --follow-tags` after to push the flags too.
- Use `cz bump` for meaningful version update, it will handle the rest.

## 2. Deploying
- Initilize gcloud CLI and log into your account
```
gcloud init
```
- Deploying to `athena` stage
```
gcloud app deploy athena.yaml 
```

### 2.1 Manage Dependencies 
- Export `uv` dependencies to `requirements.txt` for gcloud
```
uv pip compile pyproject.toml -o requirements.txt
```

### 2.2 Key commands
- Open deployed app
```
gcloud app browse
```
- Check logs
```
gcloud app logs tail -s athena
```