# Repository Module

Utilities for cloning and identifying Git repositories.

## Usage

```python
from pygrad import clone_repository, get_repository_id

# Get repository identifier from URL
repo_id = get_repository_id("https://github.com/owner/repo")
# Returns: "owner_repo"

# Clone a repository
clone_repository("https://github.com/owner/repo", "./repos/owner_repo")
```

---

## Functions

### get_repository_id

```python
def get_repository_id(url: str) -> str
```

Extract a unique identifier from a GitHub repository URL.

The identifier is created by combining the owner and repository name with an underscore,
making it safe for use as a directory name or dataset identifier.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `url` | `str` | GitHub repository URL |

**Returns:** `str` - Repository identifier in format `owner_repo`

**Example:**

```python
from pygrad import get_repository_id

# Standard GitHub URL
repo_id = get_repository_id("https://github.com/psf/requests")
print(repo_id)  # "psf_requests"

# URL with .git suffix
repo_id = get_repository_id("https://github.com/pallets/flask.git")
print(repo_id)  # "pallets_flask"

# URL with trailing slash
repo_id = get_repository_id("https://github.com/django/django/")
print(repo_id)  # "django_django"
```

**URL Formats Supported:**

- `https://github.com/owner/repo`
- `https://github.com/owner/repo.git`
- `https://github.com/owner/repo/`
- `git@github.com:owner/repo.git`

---

### clone_repository

```python
def clone_repository(url: str, target_path: str | Path) -> None
```

Clone a Git repository to the specified path.

Uses `git clone --depth 1` for a shallow clone to minimize disk usage and download time.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `url` | `str` | Git repository URL |
| `target_path` | `str \| Path` | Local path to clone to |

**Returns:** `None`

**Raises:**

- `subprocess.CalledProcessError`: If git clone fails

**Example:**

```python
from pathlib import Path
from pygrad import clone_repository, get_repository_id

url = "https://github.com/psf/requests"
repo_id = get_repository_id(url)
target = Path("./repos") / repo_id

if not target.exists():
    clone_repository(url, target)
    print(f"Cloned to: {target}")
else:
    print(f"Repository already exists: {target}")
```

---

## Configuration

Repository storage location is configured via the `PYGRAD_HOME` environment variable:

```python
from pygrad import PYGRAD_HOME, REPO_STORAGE

print(f"Pygrad home: {PYGRAD_HOME}")
print(f"Repository storage: {REPO_STORAGE}")
```

**Environment Variables:**

| Variable | Description | Default |
|----------|-------------|---------|
| `PYGRAD_HOME` | Base directory for pygrad data | `~/.pygrad` |

**Directory Structure:**

```
~/.pygrad/
├── repos/           # Cloned repositories
│   ├── owner_repo1/
│   └── owner_repo2/
└── ...
```
