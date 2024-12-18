# XBRL Toolkit

A comprehensive Python toolkit for processing, validating, and analyzing XBRL (eXtensible Business Reporting Language) and Inline XBRL (iXBRL) documents. This toolkit provides robust support for financial regulatory reporting data formats with features including validation, calculation verification, and data export capabilities.

## Features

- **Multiple Format Support**
  - Standard XBRL documents
  - Inline XBRL (iXBRL) documents
  - Support for regulatory taxonomies (e.g., SEC, ESMA)

- **Document Processing**
  - Automated discovery and processing of related XBRL files
  - Context and unit validation
  - Fact extraction and validation
  - Calculation relationship verification
  - Support for complex taxonomies

- **Validation**
  - Schema validation
  - Calculation linkbase validation
  - Context and unit reference validation
  - Data type validation
  - Custom validation rules
  - *Note: Taxonomy validation is currently in initial development phase and not fully integrated*

- **Export Options**
  - JSON export for further processing
  - CSV export for analysis in spreadsheet applications


## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/xbrl-processor.git
cd xbrl-processor
```

2. Create and activate a virtual environment:
```bash
# On Windows
python -m venv venv
venv\Scripts\activate

# On macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

3. Install the required dependencies:
```bash
pip install -r requirements.txt
```


## Usage

The toolkit provides a command-line interface through `xbrl_toolkit.py`:

### Basic Usage

```bash
python xbrl_toolkit.py <input_path> [options]
```

Where `<input_path>` can be either:
- A single XBRL/iXBRL file
- A directory containing multiple XBRL files

### Command Line Options

- `--validate`: Perform validation checks on the XBRL document(s)
- `--export-json <filename>`: Export the processed data to JSON format
- `--export-csv <filename>`: Export the processed data to CSV format

### Examples

Process and validate a single XBRL file:
```bash
python xbrl_toolkit.py example.xml --validate
```

Process a folder and export to both JSON and CSV:
```bash
python xbrl_toolkit.py ./xbrl_files/ --validate --export-json output.json --export-csv output.csv
```

## Project Structure

```
xbrl-processor/
├── core/                     # Core processing functionality
│   ├── processor.py         # Main XBRL processing logic
│   ├── inline_processor.py  # iXBRL processing logic
│   ├── folder_processor.py  # Multi-file processing
│   └── models.py           # Data models
├── validators/              # Validation components
│   ├── calculation_validator.py   # Calculation validation
│   └── taxonomy_validator.py      # Taxonomy validation (in development)
├── tests/                  # Test suite
├── examples/               # Example files
└── xbrl_toolkit.py        # Command-line interface
```

## Example Files

The repository includes example files for testing and demonstration:

- **Novartis Example**: Sourced from the official XBRL sample files repository, providing a comprehensive example of standard XBRL format
- **SEC EDGAR Examples**: Additional examples obtained from the SEC's EDGAR database, demonstrating real-world iXBRL implementations

These examples are included for testing purposes and to demonstrate the toolkit's capabilities with both standard XBRL and modern iXBRL formats.

## Validation Features

The toolkit performs several types of validation:

1. **Context Validation**
   - Entity identifier presence and format
   - Period type consistency
   - Context reference validity

2. **Unit Validation**
   - Unit reference consistency
   - Standard unit type verification
   - Complex unit relationship validation

3. **Calculation Validation**
   - Mathematical relationship verification
   - Cross-context calculation consistency
   - Weight and balance validation

4. **Taxonomy Validation** (In Development)
   - Basic schema compliance
   - Data type verification
   - Required attribute validation
   - *Note: This feature is currently in early development and may not be fully functional*

## Data Export

### JSON Export
Exports a structured JSON document containing:
- All contexts with their periods and scenarios
- Units with their measures
- Facts with their values and references
- Calculation relationships

### CSV Export
Creates a flattened CSV file with:
- One fact per row
- Associated context and unit information
- Values and references
- Perfect for spreadsheet analysis

## Testing

Run the test suite using pytest:
```bash
pytest tests/
```

## Requirements

- Python 3.8+
- lxml>=4.9.3
- numpy>=1.24.0
- pandas>=2.0.0
- requests>=2.31.0
- pytest>=8.0.0 (for testing)

