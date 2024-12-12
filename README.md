# XBRL Processing Toolkit

A Python library for parsing, validating, and processing XBRL (eXtensible Business Reporting Language) documents. Built with a focus on financial regulatory reporting, this toolkit provides comprehensive support for working with XBRL instance documents and taxonomies.

## Features

- **Complete XBRL Document Processing**
  - Parse XBRL instance documents
  - Handle both standard and inline XBRL formats
  - Support for context and unit definitions
  - Process fact values with type conversion

- **Robust Validation**
  - Context reference validation
  - Unit reference validation for numeric facts
  - Taxonomy validation support
  - Calculation consistency checks

- **Data Export Options**
  - Export to JSON format
  - Export to CSV format
  - Structured data output for analysis

- **Advanced Features**
  - Support for duration and instant contexts
  - Handle complex unit definitions including divide relationships
  - Process scenario information
  - Comprehensive taxonomy support

## Installation

```bash
# Clone the repository
git clone https://github.com/nkurien/xbrl-processor.git
cd xbrl-processor

# Install dependencies
pip install -r requirements.txt
```

## Dependencies

- lxml>=4.9.3
- numpy>=1.24.0
- pandas>=2.0.0
- requests>=2.31.0
- pytest>=8.0.0
- pytest-cov>=4.1.0

## Usage

### Command Line Interface

The toolkit provides a command-line interface for basic operations:

```bash
# Validate an XBRL file
python cli.py input.xbrl --validate

# Export to JSON
python cli.py input.xbrl --export-json output.json

# Export to CSV
python cli.py input.xbrl --export-csv output.csv
```

### Python API

```python
from xbrl_processor import XBRLProcessor
from pathlib import Path

# Initialize processor
processor = XBRLProcessor()

# Load and process XBRL instance
processor.load_instance(Path("example.xbrl"))

# Load taxonomy (optional)
processor.load_taxonomy(Path("taxonomy.xsd"))

# Validate
errors = processor.validate()
if errors:
    print("Validation errors found:")
    for error in errors:
        print(f"- {error}")

# Export data
processor.export_to_json(Path("output.json"))
processor.export_to_csv(Path("output.csv"))
```

## Core Components

### XBRLContext

Handles period and entity information:

```python
@dataclass
class XBRLContext:
    id: str
    entity: str
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    instant: Optional[datetime] = None
    scenario: Optional[Dict[str, Any]] = None
```

### XBRLUnit

Represents unit definitions:

```python
@dataclass
class XBRLUnit:
    id: str
    measures: List[str]  # e.g., ['iso4217:USD']
    divide: bool = False
    numerator: List[str] = field(default_factory=list)
    denominator: List[str] = field(default_factory=list)
```

### XBRLFact

Represents individual XBRL facts:

```python
@dataclass
class XBRLFact:
    concept: str
    value: Any
    context_ref: str
    unit_ref: Optional[str] = None
    decimals: Optional[int] = None
    precision: Optional[int] = None
```


## Testing

The project includes comprehensive test coverage using pytest:

```bash
# Run tests
pytest

# Run tests with coverage report
pytest --cov=xbrl_processor
```

## Future Development

Planned enhancements include:
1. Enhanced taxonomy validation support
2. Support for more regulatory-specific taxonomies (FCA/Bank of England)
3. Batch processing capabilities
4. Additional export formats
5. XBRL calculations validation
6. Support for extension taxonomies
