import pytest
from pathlib import Path
from datetime import datetime
import shutil
from decimal import Decimal
from lxml import etree
from processor import XBRLProcessor, XBRLContext, XBRLUnit, XBRLFact, XBRLFolderProcessor


@pytest.fixture
def processor():
    """Provide a fresh XBRLProcessor instance for each test."""
    return XBRLProcessor()


@pytest.fixture
def sample_contexts():
    """Provide standard test contexts."""
    return {
        'ctx1': XBRLContext(
            id='ctx1',
            entity='http://entity.com:TEST',
            instant=datetime(2024, 1, 1)
        ),
        'ctx2': XBRLContext(
            id='ctx2',
            entity='http://entity.com:TEST',
            period_start=datetime(2024, 1, 1),
            period_end=datetime(2024, 12, 31)
        )
    }


def test_fact_parsing(processor, sample_contexts):
    """Test comprehensive fact parsing with different types and attributes."""
    xml = """
    <xbrl xmlns:xbrli="http://www.xbrl.org/2001/instance" 
          xmlns:test="http://test.namespace"
          xmlns:iso4217="http://www.xbrl.org/2003/iso4217">
        <test:Revenue contextRef="ctx1" unitRef="usd" decimals="2" precision="INF" sign="-">1000.00</test:Revenue>
        <test:Shares contextRef="ctx1" unitRef="shares" precision="4">500000</test:Shares>
        <test:Ratio contextRef="ctx1" unitRef="pure" decimals="4">0.5432</test:Ratio>
        <test:Description contextRef="ctx1">Test description with special chars: &amp; &lt; &gt;</test:Description>
    </xbrl>
    """

    # Setup processor
    root = etree.fromstring(xml)
    processor.namespaces['test'] = 'http://test.namespace'
    processor.contexts.update(sample_contexts)
    processor.units.update({
        'usd': XBRLUnit(id='usd', measures=['iso4217:USD']),
        'shares': XBRLUnit(id='shares', measures=['xbrli:shares']),
        'pure': XBRLUnit(id='pure', measures=['xbrli:pure'])
    })

    # Parse facts
    processor._parse_facts(root)

    # Verify correct number of facts parsed
    assert len(processor.facts) == 4, "Should parse exactly 4 facts"

    # Test numeric fact with sign and precision
    revenue = next(f for f in processor.facts if f.concept == 'test:Revenue')
    assert revenue.value == -1000.00
    assert revenue.decimals == 2
    assert revenue.precision == float('inf')
    assert revenue.unit_ref == 'usd'

    # Test integer fact with precision
    shares = next(f for f in processor.facts if f.concept == 'test:Shares')
    assert isinstance(shares.value, int)
    assert shares.value == 500000
    assert shares.precision == 4

    # Test decimal fact
    ratio = next(f for f in processor.facts if f.concept == 'test:Ratio')
    assert isinstance(ratio.value, float)
    assert ratio.value == 0.5432
    assert ratio.decimals == 4

    # Test string fact with special characters
    desc = next(f for f in processor.facts if f.concept == 'test:Description')
    assert desc.value == 'Test description with special chars: & < >'
    assert desc.unit_ref is None


def test_validation(processor, sample_contexts):
    """Test comprehensive validation including context, unit, and fact relationships."""
    # Setup test data
    processor.contexts.update(sample_contexts)
    processor.units['usd'] = XBRLUnit(id='usd', measures=['iso4217:USD'])

    # Add valid and invalid facts
    test_facts = [
        XBRLFact(concept='test:Valid', value=100, context_ref='ctx1', unit_ref='usd'),
        XBRLFact(concept='test:MissingContext', value=100, context_ref='missing', unit_ref='usd'),
        XBRLFact(concept='test:MissingUnit', value=100, context_ref='ctx1', unit_ref='missing'),
        XBRLFact(concept='test:NonNumeric', value='text', context_ref='ctx1', unit_ref='usd'),
    ]
    processor.facts.extend(test_facts)

    # Run validation
    errors = processor.validate()

    # Verify specific error messages
    error_texts = '\n'.join(errors)
    assert 'missing context' in error_texts.lower()
    assert 'missing unit' in error_texts.lower()
    assert any('numeric' in err.lower() and 'unit' in err.lower() for err in errors)

    # Count errors
    assert len(errors) == 3, "Should find exactly 3 validation errors"


def test_context_periods(processor):
    """Test comprehensive context period handling."""
    xml = """
    <xbrl xmlns:xbrli="http://www.xbrl.org/2001/instance"
          xmlns:test="http://test.com/test">
        <xbrli:context id="instant">
            <xbrli:entity>
                <xbrli:identifier scheme="http://test.com">TEST</xbrli:identifier>
            </xbrli:entity>
            <xbrli:period>
                <xbrli:instant>2024-01-01</xbrli:instant>
            </xbrli:period>
        </xbrli:context>
        <xbrli:context id="duration">
            <xbrli:entity>
                <xbrli:identifier scheme="http://test.com">TEST</xbrli:identifier>
            </xbrli:entity>
            <xbrli:period>
                <xbrli:startDate>2024-01-01</xbrli:startDate>
                <xbrli:endDate>2024-12-31</xbrli:endDate>
            </xbrli:period>
            <xbrli:scenario>
                <test:type>Actual</test:type>
            </xbrli:scenario>
        </xbrli:context>
    </xbrl>
    """

    root = etree.fromstring(xml)
    processor._parse_contexts(root)

    # Test instant context
    instant_ctx = processor.contexts['instant']
    assert instant_ctx.is_instant
    assert not instant_ctx.is_duration
    assert instant_ctx.instant == datetime(2024, 1, 1)
    assert instant_ctx.entity == 'http://test.com:TEST'

    # Test duration context
    duration_ctx = processor.contexts['duration']
    assert not duration_ctx.is_instant
    assert duration_ctx.is_duration
    assert duration_ctx.period_start == datetime(2024, 1, 1)
    assert duration_ctx.period_end == datetime(2024, 12, 31)
    assert duration_ctx.scenario is not None
    assert 'type' in duration_ctx.scenario['segments'][0]


@pytest.mark.integration
def test_real_file_loading(folder_processor):
    """Test processing of real XBRL files with comprehensive validation."""
    test_dir = Path(__file__).parent.parent
    novartis_folder = test_dir / "Novartis-2002-11-15"

    if not novartis_folder.exists():
        pytest.skip(f"Novartis test folder not found at {novartis_folder}")

    # Process the folder
    folder_processor.process_folder(novartis_folder)

    # Test context loading
    assert len(folder_processor.contexts) > 0, "No contexts were loaded"
    assert 'Group2001AsOf' in folder_processor.contexts, "Expected context not found"
    assert folder_processor.contexts['Group2001AsOf'].entity.endswith('Novartis Group')

    # Test unit loading
    assert len(folder_processor.units) > 0, "No units were loaded"
    chf_units = [u for u in folder_processor.units.values()
                 if any('CHF' in m for m in u.measures)]
    assert len(chf_units) > 0, "Expected CHF unit not found"

    # Test fact loading
    assert len(folder_processor.facts) > 0, "No facts were loaded"

    # Test specific fact values
    revenue_facts = [f for f in folder_processor.facts
                     if 'Revenue' in f.concept]
    assert len(revenue_facts) > 0, "No revenue facts found"
    assert all(isinstance(f.value, (int, float)) for f in revenue_facts), \
        "Revenue facts should be numeric"

    # Add specific data validation
    revenue_2001 = next((f for f in revenue_facts
                         if f.context_ref == 'Group2001ForPeriod'
                         and 'RevenueFunction' in f.concept), None)
    assert revenue_2001 is not None, "2001 revenue not found"
    assert revenue_2001.value == 32038000000, "Unexpected 2001 revenue value"

    # Validate full dataset
    errors = folder_processor.validate()
    assert len(errors) == 0, f"Validation errors found:\n" + "\n".join(errors)


@pytest.fixture
def folder_processor():
    """Provide a fresh XBRLFolderProcessor instance for each test."""
    return XBRLFolderProcessor()


@pytest.fixture
def novartis_folder(tmp_path):
    """Create a temporary test folder with Novartis files."""
    # First try the direct parent directory
    test_dir = Path(__file__).parent.parent
    source_folder = test_dir / "Novartis-2002-11-15"

    # If not found, try the same directory as the test file
    if not source_folder.exists():
        source_folder = test_dir / "tests" / "Novartis-2002-11-15"

    # Create the temporary folder
    novartis_folder = tmp_path / "Novartis-2002-11-15"
    novartis_folder.mkdir()

    # Define the expected Novartis files
    expected_files = [
        "Novartis-2002-11-15.xml",  # Instance document
        "Novartis-2002-11-15.xsd",  # Schema
        "Novartis-2002-11-15-calculation.xml",
        "Novartis-2002-11-15-labels.xml",
        "Novartis-2002-11-15-presentation.xml",
        "Novartis-2002-11-15-references.xml"
    ]

    if not source_folder.exists():
        # If source folder doesn't exist, let's create a minimal test file
        instance_file = novartis_folder / "Novartis-2002-11-15.xml"
        instance_file.write_text("""
        <?xml version="1.0" encoding="utf-8"?>
        <xbrl xmlns='http://www.xbrl.org/2001/instance'>
            <context id="ctx1">
                <entity>
                    <identifier scheme="http://www.test.com">TEST</identifier>
                </entity>
                <period>
                    <instant>2024-01-01</instant>
                </period>
            </context>
            <test:Revenue contextRef="ctx1">1000</test:Revenue>
        </xbrl>
        """)
        print(f"Warning: Source folder not found at {source_folder}, created minimal test file")
        return novartis_folder

    # Copy files that exist
    files_copied = 0
    for filename in expected_files:
        source_file = source_folder / filename
        if source_file.exists():
            shutil.copy2(source_file, novartis_folder / filename)
            files_copied += 1
        else:
            print(f"Warning: Source file {filename} not found")

    if files_copied == 0:
        pytest.skip(f"No Novartis test files found in {source_folder}")

    return novartis_folder


def test_folder_processor_initialization(folder_processor):
    """Test the folder processor initializes correctly."""
    assert folder_processor.base_processor is not None
    assert isinstance(folder_processor.discovered_files, dict)


def test_file_discovery(folder_processor, novartis_folder):
    """Test XBRL file discovery and categorization."""
    # Print debug information about the test folder
    print("\nDebug: Contents of test folder:")
    for file in novartis_folder.iterdir():
        print(f"  {file.name}")

    folder_processor._discover_files(novartis_folder)

    print("\nDebug: Discovered files:")
    for name, file in folder_processor.discovered_files.items():
        print(f"  {name}: {file.file_type}")

    discovered_types = {f.file_type for f in folder_processor.discovered_files.values()}
    assert len(folder_processor.discovered_files) > 0, "No files were discovered"
    assert 'instance' in discovered_types, "No instance document found"


def test_full_folder_processing(folder_processor, novartis_folder):
    """Test end-to-end folder processing."""
    print("\nDebug: Files in test folder:")
    for file in novartis_folder.iterdir():
        print(f"  {file.name}")

    folder_processor.process_folder(novartis_folder)

    # Basic data presence checks
    assert len(folder_processor.contexts) > 0, "No contexts were loaded"
    assert len(folder_processor.facts) > 0, "No facts were loaded"


def test_invalid_folder_handling(folder_processor, tmp_path):
    """Test handling of invalid folders and files."""
    empty_folder = tmp_path / "empty"
    empty_folder.mkdir()

    with pytest.raises(ValueError, match="No XBRL or iXBRL instance document found"):
        folder_processor.process_folder(empty_folder)

    with pytest.raises(ValueError, match="is not a directory"):
        folder_processor.process_folder(tmp_path / "nonexistent")


def test_export_functionality(folder_processor, novartis_folder, tmp_path):
    """Test export functionality with folder processor."""
    folder_processor.process_folder(novartis_folder)

    # Test JSON export
    json_path = tmp_path / "output.json"
    folder_processor.export_to_json(json_path)
    assert json_path.exists()
    assert json_path.stat().st_size > 0, "JSON file is empty"

    # Test CSV export
    csv_path = tmp_path / "output.csv"
    folder_processor.export_to_csv(csv_path)
    assert csv_path.exists()
    assert csv_path.stat().st_size > 0, "CSV file is empty"