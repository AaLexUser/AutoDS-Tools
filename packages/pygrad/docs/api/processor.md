# Processor Module

The processor module handles Python code analysis and XML API documentation generation.

## Usage

```python
from pygrad import process_repository, PythonRepositoryProcessor

# High-level: Process entire repository
await process_repository(
    repository_path="./my-repo",
    output_file="api.xml"
)

# Low-level: Use processor directly
processor = PythonRepositoryProcessor("./my-repo")
processor.process()
xml_output = processor.to_xml()
```

---

## Functions

### process_repository

```python
async def process_repository(
    repository_path: str,
    output_file: str = "api.xml"
) -> None
```

Process a Python repository and generate XML API documentation.

This is the high-level function that orchestrates the entire processing pipeline:

1. Scans for Python files
2. Parses each file with TreeSitter
3. Extracts classes, functions, and docstrings
4. Generates structured XML output

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `repository_path` | `str` | - | Path to the repository root |
| `output_file` | `str` | `"api.xml"` | Output filename (relative to repository) |

**Returns:** `None`

**Example:**

```python
from pygrad import process_repository

# Process a local repository
await process_repository(
    repository_path="/path/to/repo",
    output_file="docs/api.xml"
)
```

---

## Classes

### PythonRepositoryProcessor

```python
class PythonRepositoryProcessor:
    def __init__(self, repository_path: str) -> None
```

Low-level processor for extracting API information from Python repositories.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `repository_path` | `str` | Path to the repository root |

**Attributes:**

| Name | Type | Description |
|------|------|-------------|
| `repository_path` | `str` | Repository path |
| `classes` | `list[ClassInfo]` | Extracted class information |
| `functions` | `list[FunctionInfo]` | Extracted function information |

#### Methods

##### process

```python
def process(self) -> None
```

Process all Python files in the repository.

Recursively finds and parses all `.py` files, extracting class and function definitions.

**Example:**

```python
from pygrad import PythonRepositoryProcessor

processor = PythonRepositoryProcessor("./my-repo")
processor.process()

print(f"Found {len(processor.classes)} classes")
print(f"Found {len(processor.functions)} functions")
```

##### to_xml

```python
def to_xml(self) -> str
```

Generate XML representation of the extracted API.

**Returns:** `str` - XML string containing the API documentation

**Example:**

```python
from pygrad import PythonRepositoryProcessor

processor = PythonRepositoryProcessor("./my-repo")
processor.process()
xml_output = processor.to_xml()

# Save to file
with open("api.xml", "w") as f:
    f.write(xml_output)
```

---

### ClassInfo

```python
@dataclass
class ClassInfo:
    name: str
    docstring: str | None
    methods: list[FunctionInfo]
    bases: list[str]
    file_path: str
    line_number: int
```

Data class representing a Python class.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Class name |
| `docstring` | `str \| None` | Class docstring |
| `methods` | `list[FunctionInfo]` | Class methods |
| `bases` | `list[str]` | Base class names |
| `file_path` | `str` | Source file path |
| `line_number` | `int` | Line number in source |

---

### FunctionInfo

```python
@dataclass
class FunctionInfo:
    name: str
    docstring: str | None
    parameters: list[str]
    return_type: str | None
    decorators: list[str]
    file_path: str
    line_number: int
```

Data class representing a Python function or method.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Function name |
| `docstring` | `str \| None` | Function docstring |
| `parameters` | `list[str]` | Parameter names |
| `return_type` | `str \| None` | Return type annotation |
| `decorators` | `list[str]` | Decorator names |
| `file_path` | `str` | Source file path |
| `line_number` | `int` | Line number in source |

---

## XML Output Format

The processor generates XML in the following structure:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<api>
  <classes>
    <class name="MyClass" file="src/module.py" line="10">
      <docstring>Class description.</docstring>
      <bases>
        <base>BaseClass</base>
      </bases>
      <methods>
        <method name="my_method" line="15">
          <docstring>Method description.</docstring>
          <parameters>
            <param>self</param>
            <param>arg1: str</param>
          </parameters>
          <return_type>bool</return_type>
        </method>
      </methods>
    </class>
  </classes>
  
  <functions>
    <function name="helper_func" file="src/utils.py" line="5">
      <docstring>Function description.</docstring>
      <parameters>
        <param>x: int</param>
        <param>y: int</param>
      </parameters>
      <return_type>int</return_type>
      <decorators>
        <decorator>staticmethod</decorator>
      </decorators>
    </function>
  </functions>
</api>
```

---

## Advanced Usage

### Custom File Filtering

```python
from pygrad import PythonRepositoryProcessor
from pathlib import Path

class CustomProcessor(PythonRepositoryProcessor):
    def _should_process_file(self, path: Path) -> bool:
        # Skip test files
        if "test" in path.parts:
            return False
        # Skip private modules
        if path.stem.startswith("_"):
            return False
        return super()._should_process_file(path)

processor = CustomProcessor("./my-repo")
processor.process()
```

### Extracting Specific Information

```python
from pygrad import PythonRepositoryProcessor

processor = PythonRepositoryProcessor("./my-repo")
processor.process()

# Find all async functions
async_funcs = [
    f for f in processor.functions
    if "async" in f.decorators or f.name.startswith("async_")
]

# Find classes with specific base
api_classes = [
    c for c in processor.classes
    if "APIBase" in c.bases
]

# Find decorated methods
route_handlers = [
    m for c in processor.classes
    for m in c.methods
    if any("route" in d for d in m.decorators)
]
```
