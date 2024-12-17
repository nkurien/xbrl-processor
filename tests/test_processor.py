import pytest
from pathlib import Path
from datetime import datetime
import shutil
from decimal import Decimal
from lxml import etree
from processor import XBRLProcessor, XBRLContext, XBRLUnit, XBRLFact, XBRLFolderProcessor, iXBRLProcessor


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


@pytest.fixture
def ixbrl_processor():
    """Provide a fresh iXBRLProcessor instance for each test."""
    return iXBRLProcessor()


@pytest.fixture
def sample_ixbrl():
    """Provide sample iXBRL content with modern features."""
    xml_str = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" 
      xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"
      xmlns:ixt="http://www.xbrl.org/inlineXBRL/transformation/2020-02-12"
      xmlns:xbrli="http://www.xbrl.org/2001/instance"
      xmlns:us-gaap="http://fasb.org/us-gaap/2021"
      xmlns:dei="http://xbrl.sec.gov/dei/2021">
    <head>
        <meta charset="UTF-8"/>
        <title>Test iXBRL Document</title>
    </head>
    <body>
        <div style="display:none">
            <ix:hidden>
                <xbrli:context id="FY2023">
                    <xbrli:entity>
                        <xbrli:identifier scheme="http://www.sec.gov/CIK">0000789019</xbrli:identifier>
                    </xbrli:entity>
                    <xbrli:period>
                        <xbrli:instant>2023-12-31</xbrli:instant>
                    </xbrli:period>
                </xbrli:context>
                <xbrli:unit id="USD">
                    <xbrli:measure>iso4217:USD</xbrli:measure>
                </xbrli:unit>
                <xbrli:unit id="shares">
                    <xbrli:measure>xbrli:shares</xbrli:measure>
                </xbrli:unit>
            </ix:hidden>
        </div>
        <div>
            <p>Revenue for the year: 
                <ix:nonFraction name="us-gaap:Revenue" 
                              contextRef="FY2023" 
                              unitRef="USD" 
                              decimals="-6"
                              format="ixt:numdotdecimal"
                              scale="6">386,017</ix:nonFraction> million
            </p>
            <p>Shares outstanding: 
                <ix:nonFraction name="us-gaap:SharesOutstanding" 
                              contextRef="FY2023" 
                              unitRef="shares" 
                              format="ixt:numcommadot">15,725,449</ix:nonFraction>
            </p>
            <p>Company name: 
                <ix:nonNumeric name="dei:EntityRegistrantName" 
                             contextRef="FY2023">Meta Platforms, Inc.</ix:nonNumeric>
            </p>
        </div>
    </body>
</html>"""
    return xml_str.encode('utf-8')


def test_ixbrl_hidden_section_parsing(ixbrl_processor, sample_ixbrl):
    """Test parsing of the hidden section containing contexts and units."""
    root = etree.fromstring(sample_ixbrl)
    hidden = root.find('.//ix:hidden', ixbrl_processor.namespaces)
    assert hidden is not None

    ixbrl_processor._parse_hidden_section(hidden)

    # Test contexts
    assert 'FY2023' in ixbrl_processor.contexts
    context = ixbrl_processor.contexts['FY2023']
    assert context.entity == 'http://www.sec.gov/CIK:0000789019'
    assert context.instant == datetime(2023, 12, 31)

    # Test units
    assert 'USD' in ixbrl_processor.units
    assert 'shares' in ixbrl_processor.units
    usd_unit = ixbrl_processor.units['USD']
    assert 'iso4217:USD' in usd_unit.measures


def test_ixbrl_transformations(ixbrl_processor):
    """Test various iXBRL transformation rules."""

    def check_transform(input_val, format_type, expected):
        elem = etree.Element(f'{{{ixbrl_processor.namespaces["ix"]}}}nonFraction',
                             format=format_type,
                             name="test:value",
                             contextRef="ctx1")
        elem.text = input_val
        fact = ixbrl_processor._process_ixbrl_fact(elem)
        assert str(fact.value) == expected, f"Transform {format_type} failed for {input_val}"

    test_cases = [
        ('1,234.56', 'ixt:numdotdecimal', '1234.56'),
        ('1.234,56', 'ixt:numcommadot', '1234.56'),
        ('(1234.56)', 'ixt:numdotdecimal', '-1234.56'),
        ('12.5%', 'ixt:numwordsen', '12.5'),
        ('$1,234.56', 'ixt:numdotdecimal', '1234.56'),
        ('€1.234,56', 'ixt:numcommadot', '1234.56'),
        ('123.456.789,01', 'ixt:numcommadot', '123456789.01'),
        ('(123,456.78)', 'ixt:numdotdecimal', '-123456.78')
    ]

    for input_val, format_type, expected in test_cases:
        check_transform(input_val, format_type, expected)


def test_ixbrl_scale_handling(ixbrl_processor):
    """Test handling of scale factors in iXBRL facts."""
    test_cases = [
        # (input value, scale, format, expected result)
        ('1000', '3', 'ixt:numdotdecimal', '1000000'),
        ('1000', '-3', 'ixt:numdotdecimal', '1'),
        ('1234.5', '6', 'ixt:numdotdecimal', '1234500000'),
        ('0.001234', '-3', 'ixt:numdotdecimal', '0.000001234'),
        # Add some edge cases
        ('0', '3', 'ixt:numdotdecimal', '0'),
        ('-1000', '3', 'ixt:numdotdecimal', '-1000000'),
        ('1.23456', '-2', 'ixt:numdotdecimal', '0.0123456')
    ]

    for value, scale, format_type, expected in test_cases:
        # Create test element
        elem = etree.Element(
            f'{{{ixbrl_processor.namespaces["ix"]}}}nonFraction',
            name="test:value",
            contextRef="ctx1",
            scale=scale,
            format=format_type
        )
        elem.text = value

        # Process the fact
        fact = ixbrl_processor._process_ixbrl_fact(elem)

        # Convert both expected and actual to Decimal for comparison
        expected_decimal = Decimal(expected)
        actual_decimal = Decimal(str(fact.value))

        assert actual_decimal == expected_decimal, \
            f"Scale {scale} failed for {value}. Expected {expected}, got {fact.value}"


def test_ixbrl_error_handling(ixbrl_processor):
    """Test error handling for malformed iXBRL content."""
    malformed_cases = [
        '<ix:nonFraction xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" scale="invalid">1000</ix:nonFraction>',
        '<ix:nonFraction xmlns:ix="http://www.xbrl.org/2013/inlineXBRL">1000</ix:nonFraction>',
        '<ix:nonFraction xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" format="invalid">1000</ix:nonFraction>'
    ]

    for xml in malformed_cases:
        try:
            elem = etree.fromstring(xml.encode('utf-8'))
            fact = ixbrl_processor._process_ixbrl_fact(elem)
            assert fact is None or fact.value is None, f"Should handle malformed element: {xml}"
        except (etree.XMLSyntaxError, ValueError):
            continue


@pytest.mark.integration
def test_full_ixbrl_document_processing(ixbrl_processor, tmp_path, sample_ixbrl):
    """Integration test for processing a complete iXBRL document."""
    # Create a test file with the sample content
    test_file = tmp_path / "test.xhtml"
    test_file.write_bytes(sample_ixbrl)

    # Process the document
    ixbrl_processor.load_ixbrl_instance(test_file)

    # Basic validations
    assert len(ixbrl_processor.contexts) > 0, "No contexts loaded"
    assert len(ixbrl_processor.units) > 0, "No units loaded"
    assert len(ixbrl_processor.facts) > 0, "No facts loaded"

    # Test specific fact values
    facts = {f.concept: f for f in ixbrl_processor.facts}

    assert 'us-gaap:Revenue' in facts
    revenue = facts['us-gaap:Revenue']
    assert Decimal(revenue.value) == Decimal('386017000000')

    assert 'dei:EntityRegistrantName' in facts
    company = facts['dei:EntityRegistrantName']
    assert company.value == 'Meta Platforms, Inc.'
    assert company.unit_ref is None


def test_nested_ixbrl_facts(ixbrl_processor):
    """Test handling of nested iXBRL facts."""
    nested_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <html xmlns="http://www.w3.org/1999/xhtml" 
          xmlns:ix="http://www.xbrl.org/2013/inlineXBRL">
        <body>
            <div>
                <ix:nonFraction name="test:total" contextRef="ctx1">
                    <ix:nonFraction name="test:part1" contextRef="ctx1">100</ix:nonFraction> +
                    <ix:nonFraction name="test:part2" contextRef="ctx1">200</ix:nonFraction>
                </ix:nonFraction>
            </div>
        </body>
    </html>"""

    root = etree.fromstring(nested_xml)
    facts = list(ixbrl_processor._parse_ixbrl_facts(root))

    # Should extract all facts
    assert len(facts) == 3
    concepts = {f.concept for f in facts}
    assert concepts == {'test:total', 'test:part1', 'test:part2'}