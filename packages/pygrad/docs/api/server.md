# REST Server

PyGrad exposes a lightweight FastAPI server that mirrors every CLI command as an HTTP endpoint.

## Running the server

Install the `server` extras and start with `uvicorn`:

```bash
pip install pygrad[server]
uvicorn pygrad.server:app --host 0.0.0.0 --port 8000
```

Interactive API docs are available at `http://localhost:8000/docs` once the server is up.

---

## Endpoints

### Index a repository

```http
POST /repos
Content-Type: application/json

{"url": "https://github.com/owner/repo"}
```

Equivalent CLI command: `pygrad add <url>`

Indexing (clone + parse + knowledge-graph build) runs in the background.
The endpoint returns **202 Accepted** immediately.

**Response**

```json
{"message": "Indexing started", "url": "https://github.com/owner/repo"}
```

---

### List indexed repositories

```http
GET /repos
```

Equivalent CLI command: `pygrad list`

**Response**

```json
[{"name": "owner-repo"}, {"name": "another-repo"}]
```

---

### Search a repository

```http
POST /repos/search
Content-Type: application/json

{"url": "https://github.com/owner/repo", "query": "How do I …?"}
```

Equivalent CLI command: `pygrad ask <url> <query>`

Returns `"The library is not yet indexed."` when the repository has not been indexed yet.

**Response**

```json
{"result": "…"}
```

---

### Delete a repository

```http
DELETE /repos?url=https://github.com/owner/repo
```

Equivalent CLI command: `pygrad delete <url>`

Removes the knowledge-graph data for the repository. The local clone cache is kept on disk.

**Response**

```json
{"message": "Deleted", "url": "https://github.com/owner/repo"}
```

---

### Visualize the knowledge graph

```http
GET /visualize
```

Equivalent CLI command: `pygrad visualize`

Returns a self-contained interactive HTML page. Render it directly in a browser or save to a file.

**Response**

`text/html` — a complete HTML document.
