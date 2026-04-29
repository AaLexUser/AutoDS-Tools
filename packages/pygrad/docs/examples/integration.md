# Integration

Learn how to integrate Pygrad with popular frameworks and tools.

## FastAPI Integration

Build a documentation search API:

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pygrad as pg

app = FastAPI(title="Documentation Search API")


class IndexRequest(BaseModel):
    url: str


class SearchRequest(BaseModel):
    url: str
    query: str


class SearchResponse(BaseModel):
    result: str
    repository: str


@app.post("/index")
async def index_repository(request: IndexRequest):
    """Index a GitHub repository."""
    try:
        await pg.add(request.url)
        return {"status": "success", "message": f"Indexed {request.url}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search", response_model=SearchResponse)
async def search_documentation(request: SearchRequest):
    """Search indexed documentation."""
    try:
        result = await pg.search(request.url, request.query)
        return SearchResponse(
            result=result,
            repository=request.url
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/repositories")
async def list_repositories():
    """List all indexed repositories."""
    datasets = await pg.list()
    return {"repositories": [ds.name for ds in datasets]}


@app.delete("/repositories")
async def delete_repository(url: str):
    """Delete a repository from the index."""
    await pg.delete(url)
    return {"status": "success", "message": f"Deleted {url}"}
```

Run with:

```bash
uvicorn main:app --reload
```

## Jupyter Notebook Integration

Use Pygrad in Jupyter notebooks for interactive exploration:

```python
# Cell 1: Setup
import pygrad as pg

# Cell 2: Index a library you want to learn
await pg.add("https://github.com/pandas-dev/pandas")
print("Pandas indexed!")

# Cell 3: Ask questions interactively
query = "How do I read a CSV file?"
result = await pg.search("https://github.com/pandas-dev/pandas", query)
print(result)

# Cell 4: Explore more
questions = [
    "How to filter rows based on a condition?",
    "How to merge two dataframes?",
    "How to handle missing values?",
    "What's the difference between loc and iloc?",
]

for q in questions:
    print(f"\n{'='*60}")
    print(f"Q: {q}")
    print("-" * 60)
    result = await pg.search("https://github.com/pandas-dev/pandas", q)
    print(result)

# Cell 5: List all indexed libraries
datasets = await pg.list()
print("Indexed libraries:")
for ds in datasets:
    print(f"  - {ds.name}")
```

## Streamlit Integration

Build an interactive documentation explorer:

```python
# app.py
import streamlit as st
import asyncio
import pygrad as pg


def run_async(coro):
    """Run async function in Streamlit."""
    loop = asyncio.new_event_loop()
    return loop.run_until_complete(coro)


st.title("Library Documentation Explorer")

# Sidebar for repository management
with st.sidebar:
    st.header("Repository Management")
    
    # Add repository
    url = st.text_input("Repository URL", placeholder="https://github.com/owner/repo")
    if st.button("Index Repository"):
        if url:
            with st.spinner("Indexing..."):
                run_async(pg.add(url))
            st.success(f"Indexed: {url}")
    
    # List repositories
    st.subheader("Indexed Repositories")
    datasets = run_async(pg.list())
    for ds in datasets:
        col1, col2 = st.columns([3, 1])
        col1.write(ds.name)
        if col2.button("Delete", key=ds.name):
            # Would need actual URL to delete
            st.warning("Delete functionality requires URL")

# Main content - Search
st.header("Search Documentation")

repo_url = st.selectbox(
    "Select Repository",
    options=[f"https://github.com/{ds.name.replace('-', '/', 1)}" 
             for ds in datasets] if datasets else []
)

query = st.text_input("Your Question", placeholder="How do I...?")

if st.button("Search") and repo_url and query:
    with st.spinner("Searching..."):
        result = run_async(pg.search(repo_url, query))
    st.markdown("### Answer")
    st.markdown(result)
```

Run with:

```bash
streamlit run app.py
```

## Discord Bot Integration

Create a documentation assistant bot:

```python
import discord
from discord.ext import commands
import pygrad as pg

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())


@bot.command(name="index")
async def index_repo(ctx, url: str):
    """Index a repository: !index <url>"""
    await ctx.send(f"Indexing {url}... This may take a few minutes.")
    try:
        await pg.add(url)
        await ctx.send(f"Successfully indexed: {url}")
    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name="ask")
async def ask_docs(ctx, url: str, *, query: str):
    """Ask about a library: !ask <url> <question>"""
    await ctx.send("Searching...")
    try:
        result = await pg.search(url, query)
        # Discord has a 2000 char limit
        if len(result) > 1900:
            result = result[:1900] + "..."
        await ctx.send(f"**Answer:**\n{result}")
    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name="libs")
async def list_libs(ctx):
    """List indexed libraries: !libs"""
    datasets = await pg.list()
    if datasets:
        msg = "**Indexed Libraries:**\n" + "\n".join(f"- {ds.name}" for ds in datasets)
    else:
        msg = "No libraries indexed yet. Use `!index <url>` to add one."
    await ctx.send(msg)


bot.run("YOUR_DISCORD_BOT_TOKEN")
```

## Batch Processing

Process multiple repositories efficiently:

```python
import asyncio
import pygrad as pg


async def batch_index(urls: list[str], max_concurrent: int = 3):
    """Index multiple repositories with concurrency control."""
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def index_with_semaphore(url: str):
        async with semaphore:
            print(f"Starting: {url}")
            try:
                await pg.add(url)
                print(f"Completed: {url}")
                return {"url": url, "status": "success"}
            except Exception as e:
                print(f"Failed: {url} - {e}")
                return {"url": url, "status": "error", "error": str(e)}
    
    tasks = [index_with_semaphore(url) for url in urls]
    return await asyncio.gather(*tasks)


async def batch_search(url: str, queries: list[str]) -> dict[str, str]:
    """Run multiple queries against a repository."""
    results = {}
    for query in queries:
        results[query] = await pg.search(url, query)
    return results


async def main():
    # Batch indexing
    urls = [
        "https://github.com/pydantic/pydantic",
        "https://github.com/fastapi/fastapi",
        "https://github.com/encode/httpx",
    ]
    
    results = await batch_index(urls)
    print("\nIndexing Results:")
    for r in results:
        print(f"  {r['url']}: {r['status']}")
    
    # Batch searching
    url = "https://github.com/pydantic/pydantic"
    queries = [
        "How to validate strings?",
        "How to use custom validators?",
        "How to serialize models?",
    ]
    
    search_results = await batch_search(url, queries)
    for query, answer in search_results.items():
        print(f"\nQ: {query}")
        print(f"A: {answer[:200]}...")


if __name__ == "__main__":
    asyncio.run(main())
```

## Slack Bot Integration

```python
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
import pygrad as pg

app = AsyncApp(token="xoxb-your-token")


@app.command("/pygrad-index")
async def index_command(ack, say, command):
    await ack()
    url = command["text"]
    await say(f"Indexing {url}...")
    try:
        await pg.add(url)
        await say(f"Successfully indexed: {url}")
    except Exception as e:
        await say(f"Error: {e}")


@app.command("/pygrad-ask")
async def ask_command(ack, say, command):
    await ack()
    parts = command["text"].split(" ", 1)
    if len(parts) < 2:
        await say("Usage: /pygrad-ask <url> <question>")
        return
    
    url, query = parts
    await say("Searching...")
    try:
        result = await pg.search(url, query)
        await say(f"*Answer:*\n{result}")
    except Exception as e:
        await say(f"Error: {e}")


async def main():
    handler = AsyncSocketModeHandler(app, "xapp-your-app-token")
    await handler.start_async()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

## Next Steps

- [Architecture overview](../architecture/index.md)
- [Configuration guide](../configuration/index.md)
- [API reference](../api/index.md)
