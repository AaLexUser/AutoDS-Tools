# How It Works

Detailed technical explanation of Pygrad's processing and search flows.

## Adding a Repository (`pg.add()`)

When you call `pg.add(url)`, the following sequence occurs:

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant Core as pg.add()
    participant Repo as Repository
    participant TS as TreeSitter
    participant Proc as Processor
    participant Ex as ExampleExtractor
    participant XML as XMLGenerator
    participant Cognee
    participant LLM
    
    User->>Core: pg.add("https://github.com/owner/repo")
    
    Note over Core: Phase 1: Clone Repository
    Core->>Repo: clone_repository(url, path)
    Repo->>Repo: git clone --depth 1
    Repo-->>Core: repo_path
    
    Note over Core: Phase 2: Parse Python Files
    Core->>TS: analyze_directory(repo_path)
    loop For each .py file
        TS->>TS: Parse with tree-sitter
        TS->>TS: Extract classes, functions, methods
        TS->>TS: Extract docstrings, decorators
        TS->>TS: Build imports map
    end
    TS-->>Core: project_structure
    
    Note over Core: Phase 3: Process API
    Core->>Proc: process_repository_data()
    Proc->>Proc: Build ClassInfo objects
    Proc->>Proc: Build FunctionInfo objects
    Proc->>Proc: Exclude test/example directories
    Proc-->>Core: (classes, functions)
    
    Note over Core: Phase 4: Extract Examples
    Core->>Ex: extract_examples_from_repository()
    Ex->>Ex: Find test directories
    Ex->>Ex: Find example directories
    Ex->>Ex: Parse test functions
    Ex->>Ex: Match examples to API elements
    Ex-->>Core: api_usage_groups
    
    Note over Core: Phase 5: Generate XML
    Core->>XML: generate_xml(classes, functions, examples)
    XML->>XML: Create structured XML
    XML->>XML: Include usage examples
    XML-->>Core: api.xml
    
    Note over Core: Phase 6: Index in Knowledge Graph
    Core->>Cognee: cognee.add(documents)
    Cognee->>Cognee: Split into chunks
    Cognee->>LLM: Generate embeddings
    Cognee->>Cognee: Store in vector DB
    Cognee-->>Core: documents_added
    
    Core->>Cognee: cognee.cognify()
    Cognee->>LLM: Extract entities & relationships
    Cognee->>Cognee: Build knowledge graph
    Cognee-->>Core: graph_built
    
    Core-->>User: Repository added successfully
```

### Phase Details

#### Phase 1: Clone Repository

```python
# Shallow clone for speed
git clone --depth 1 https://github.com/owner/repo /path/to/repo
```

- Uses `--depth 1` for faster cloning
- Stores in `~/.pygrad/repos/{owner}-{repo}`

#### Phase 2: Parse Python Files

Tree-sitter parses each Python file and extracts:

- **Classes**: Name, docstring, decorators, attributes
- **Methods**: Name, arguments, return type, docstring
- **Functions**: Name, arguments, return type, docstring
- **Imports**: Module paths, aliases

#### Phase 3: Process API

The processor creates structured data objects:

```python
ClassInfo(
    name="Calculator",
    api_path="mypackage.Calculator",
    description="A simple calculator class.",
    initialization={"parameters": "self, initial_value: int = 0", ...},
    methods=[FunctionInfo(...), ...],
    usage_examples=[...]
)
```

#### Phase 4: Extract Examples

The example extractor finds real usage:

- Scans `tests/`, `test/` directories
- Scans `examples/`, `example/` directories
- Parses test functions starting with `test_`
- Links examples to API elements they use

#### Phase 5: Generate XML

Structured XML documentation:

```xml
<repository>
  <important_files>
    <file score="100">core.py</file>
  </important_files>
  <class>
    <name>Calculator</name>
    <api_path>mypackage.Calculator</api_path>
    <methods>...</methods>
    <usage_examples>...</usage_examples>
  </class>
</repository>
```

#### Phase 6: Index in Knowledge Graph

Cognee processes the documentation:

1. **Chunking**: Splits XML into semantic chunks
2. **Embedding**: Generates vector embeddings
3. **Entity Extraction**: Identifies classes, methods, relationships
4. **Graph Building**: Creates connected knowledge graph

---

## Searching Documentation (`pg.search()`)

When you call `pg.search(url, query)`:

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant Core as pg.search()
    participant PS as PromptStore
    participant Cognee
    participant VDB as Vector DB
    participant GDB as Graph DB
    participant LLM
    
    User->>Core: pg.search(url, "How to validate emails?")
    
    Note over Core: Phase 1: Resolve Dataset
    Core->>Core: get_repository_id(url)
    Core->>Cognee: get_dataset("owner-repo")
    Cognee-->>Core: dataset
    
    alt Dataset not found
        Core-->>User: "The library is not yet indexed."
    end
    
    Note over Core: Phase 2: Load System Prompt
    Core->>PS: load("grad.md")
    PS-->>Core: system_prompt
    
    Note over Core: Phase 3: Search Knowledge Graph
    Core->>Cognee: cognee.search(query, dataset_ids, system_prompt)
    
    Cognee->>LLM: Generate query embedding
    LLM-->>Cognee: query_vector
    
    Cognee->>VDB: Similarity search
    VDB-->>Cognee: relevant_chunks
    
    Cognee->>GDB: Get connected nodes
    GDB-->>Cognee: graph_context
    
    Note over Cognee: Context Extension
    Cognee->>Cognee: Combine chunks + graph context
    
    Cognee->>LLM: Generate answer
    Note right of LLM: System prompt + Context + Query
    LLM-->>Cognee: answer
    
    Cognee-->>Core: search_result
    
    Core-->>User: Formatted answer
```

### Search Phases

#### Phase 1: Resolve Dataset

```python
repo_id = get_repository_id("https://github.com/owner/repo")
# Returns: "owner-repo"

dataset = await get_dataset(repo_id)
# Returns: Dataset object or None
```

#### Phase 2: Load System Prompt

The system prompt instructs the LLM how to answer:

```markdown
You are the definitive technical documentation expert for this library.
Adopt a clear, instructional tone focused on helping developers...
```

#### Phase 3: Search Knowledge Graph

1. **Query Embedding**: Convert question to vector
2. **Similarity Search**: Find relevant documentation chunks
3. **Graph Context**: Expand with related entities (classes methods reference)
4. **LLM Generation**: Generate comprehensive answer

---

## Listing Repositories (`pg.list()`)

```mermaid
sequenceDiagram
    participant User
    participant Core as pg.list()
    participant Cognee
    participant DB as Database
    
    User->>Core: pg.list()
    Core->>Cognee: cognee.datasets.list_datasets()
    Cognee->>DB: Query all datasets
    DB-->>Cognee: dataset_list
    Cognee-->>Core: [Dataset, Dataset, ...]
    Core-->>User: datasets
```

---

## Deleting a Repository (`pg.delete()`)

```mermaid
sequenceDiagram
    participant User
    participant Core as pg.delete()
    participant Cognee
    participant VDB as Vector DB
    participant GDB as Graph DB
    
    User->>Core: pg.delete(url)
    Core->>Core: get_repository_id(url)
    Core->>Cognee: get_dataset("owner-repo")
    Cognee-->>Core: dataset
    
    alt Dataset exists
        Core->>Cognee: delete_dataset(dataset.id)
        Cognee->>VDB: Remove vectors
        Cognee->>GDB: Remove graph nodes
        Cognee-->>Core: deleted
    end
    
    Core-->>User: Repository deleted
```

---

## Processing Pipeline Detail

```mermaid
flowchart TD
    subgraph Input
        URL[GitHub URL]
        LOCAL[Local Path]
    end
    
    subgraph Clone["1. Repository Clone"]
        GIT[git clone --depth 1]
        PATH[~/.pygrad/repos/owner-repo]
    end
    
    subgraph Parse["2. Tree-sitter Parse"]
        WALK[Walk .py files]
        AST[Build AST]
        STRUCT[Extract structure]
    end
    
    subgraph Process["3. API Processing"]
        CLASS[ClassInfo]
        FUNC[FunctionInfo]
        FILTER[Filter private/test]
    end
    
    subgraph Examples["4. Example Extraction"]
        TEST[Scan tests/]
        EXAMPLE[Scan examples/]
        MATCH[Match to API]
    end
    
    subgraph Generate["5. XML Generation"]
        XML[api.xml]
        PRETTY[Pretty print]
    end
    
    subgraph Index["6. Knowledge Graph"]
        CHUNK[Chunk documents]
        EMBED[Generate embeddings]
        ENTITY[Extract entities]
        GRAPH[Build graph]
    end
    
    URL --> GIT --> PATH
    LOCAL --> PATH
    PATH --> WALK --> AST --> STRUCT
    STRUCT --> CLASS & FUNC
    CLASS & FUNC --> FILTER
    FILTER --> TEST & EXAMPLE
    TEST & EXAMPLE --> MATCH
    MATCH --> XML --> PRETTY
    PRETTY --> CHUNK --> EMBED --> ENTITY --> GRAPH
```

## Next Steps

- [Components](components.md) - Detailed component descriptions
- [Configuration](../configuration/index.md) - LLM and database setup
- [API Reference](../api/index.md) - Function signatures and parameters
