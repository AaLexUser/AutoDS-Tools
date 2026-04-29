# Search Queries

Learn how to craft effective search queries to get the best results from Pygrad.

## Query Types

### Conceptual Questions

Ask about high-level concepts and patterns:

```python
import pygrad as pg

url = "https://github.com/pydantic/pydantic"

# Understanding concepts
await pg.search(url, "What is data validation in Pydantic?")
await pg.search(url, "Explain the difference between BaseModel and dataclass")
await pg.search(url, "How does Pydantic handle type coercion?")
```

### How-To Questions

Ask step-by-step guidance:

```python
# Task-oriented queries
await pg.search(url, "How do I create a model with optional fields?")
await pg.search(url, "How to validate nested objects?")
await pg.search(url, "How can I add custom validation logic?")
```

### API-Specific Questions

Ask about specific classes, methods, or functions:

```python
# Direct API queries
await pg.search(url, "What parameters does BaseModel accept?")
await pg.search(url, "Show the signature of the Field function")
await pg.search(url, "What methods are available on ValidationError?")
```

### Example Requests

Ask for code examples:

```python
# Example-focused queries
await pg.search(url, "Show me an example of email validation")
await pg.search(url, "Give me a code example using computed fields")
await pg.search(url, "Example of custom JSON encoder")
```

### Error and Troubleshooting

Ask about errors and edge cases:

```python
# Troubleshooting queries
await pg.search(url, "What exceptions can Pydantic raise?")
await pg.search(url, "How to handle validation errors?")
await pg.search(url, "Common mistakes when using validators?")
```

## Query Patterns

### Pattern 1: The "How To" Pattern

```python
# Format: "How do I [action] [object]?"
await pg.search(url, "How do I validate a list of emails?")
await pg.search(url, "How do I serialize a model to JSON?")
await pg.search(url, "How do I create a recursive model?")
```

### Pattern 2: The "What Is" Pattern

```python
# Format: "What is [concept]?"
await pg.search(url, "What is a root validator?")
await pg.search(url, "What is the Config class for?")
await pg.search(url, "What is field serialization?")
```

### Pattern 3: The "Show Me" Pattern

```python
# Format: "Show [example/code] of [feature]"
await pg.search(url, "Show examples of using aliases")
await pg.search(url, "Show the code for custom types")
await pg.search(url, "Show how to use validators")
```

### Pattern 4: The Comparison Pattern

```python
# Format: "What is the difference between [A] and [B]?"
await pg.search(url, "What is the difference between validator and field_validator?")
await pg.search(url, "Difference between model_dump and dict?")
await pg.search(url, "When to use Field vs Annotated?")
```

### Pattern 5: The Troubleshooting Pattern

```python
# Format: "Why does [problem] happen?" or "How to fix [issue]?"
await pg.search(url, "Why does validation fail for optional fields?")
await pg.search(url, "How to fix circular import with models?")
```

## Advanced Queries

### Multi-Part Questions

```python
# Combine concepts for comprehensive answers
await pg.search(
    url,
    "How do I create a model with email validation and serialize it to JSON?"
)
```

### Contextual Queries

```python
# Provide context for better answers
await pg.search(
    url,
    "I'm building a REST API. How should I handle validation errors?"
)

await pg.search(
    url,
    "For a configuration file parser, what's the best way to validate settings?"
)
```

### Querying Multiple Repositories

Search across different indexed repositories:

```python
import pygrad as pg

# Index multiple libraries
await pg.add("https://github.com/pydantic/pydantic")
await pg.add("https://github.com/fastapi/fastapi")

# Query each
pydantic_result = await pg.search(
    "https://github.com/pydantic/pydantic",
    "How to create a custom type?"
)

fastapi_result = await pg.search(
    "https://github.com/fastapi/fastapi",
    "How to define request body validation?"
)
```

## Query Best Practices

### Do's

- **Be specific**: "How to validate email format" vs "validation"
- **Use natural language**: Write queries as you would ask a colleague
- **Include context**: Mention what you're trying to achieve
- **Ask follow-up questions**: Build on previous answers

### Don'ts

- **Avoid single words**: "email" won't give good results
- **Don't be too verbose**: Keep queries focused
- **Avoid implementation details**: Ask about concepts, not line numbers

## Example: Library Exploration Session

```python
import asyncio
import pygrad as pg


async def explore_library(url: str):
    """Interactive library exploration."""
    
    # Start with overview questions
    print("=== Library Overview ===")
    overview = await pg.search(url, "What are the main features of this library?")
    print(overview)
    
    # Drill into specifics
    print("\n=== Core Concepts ===")
    concepts = await pg.search(url, "What are the key classes I should know about?")
    print(concepts)
    
    # Get practical examples
    print("\n=== Quick Start ===")
    quickstart = await pg.search(url, "Show me a simple example to get started")
    print(quickstart)
    
    # Common patterns
    print("\n=== Best Practices ===")
    patterns = await pg.search(url, "What are common patterns and best practices?")
    print(patterns)


if __name__ == "__main__":
    asyncio.run(explore_library("https://github.com/encode/httpx"))
```

## Next Steps

- [CLI usage examples](cli-usage.md)
- [Integration patterns](integration.md)
