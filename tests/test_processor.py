# test_processor.py

import pytest
from pathlib import Path
from processor import XBRLProcessor, XBRLContext, XBRLUnit, XBRLFact
from datetime import datetime
from lxml import etree


@pytest.fixture
def processor():
    """Provide a fresh XBRLProcessor instance for each test."""
    return XBRLProcessor()

@pytest.fixture
def sample_fact_xml():
    """Provide sample XML with fact definitions."""
    return """
    <xbrl xmlns:xbrli="http://www.xbrl.org/2001/instance" 
          xmlns:test="http://test.namespace">
        <test:Revenue contextRef="ctx1" unitRef="usd" decimals="2">1000.00</test:Revenue>
        <test:Description contextRef="ctx1">Test description</test:Description>
    </xbrl>
    """

@pytest.fixture
def sample_unit_xml():
    """Provide sample XML with unit definitions."""
    return """
    <xbrl xmlns:xbrli="http://www.xbrl.org/2001/instance" 
          xmlns:iso4217="http://www.xbrl.org/2003/iso4217">
        <xbrli:unit id="usd">
            <xbrli:measure>iso4217:USD</xbrli:measure>
        </xbrli:unit>
        <xbrli:unit id="ratio">
            <xbrli:divide>
                <xbrli:unitNumerator>
                    <xbrli:measure>xbrli:pure</xbrli:measure>
                </xbrli:unitNumerator>
                <xbrli:unitDenominator>
                    <xbrli:measure>xbrli:pure</xbrli:measure>
                </xbrli:unitDenominator>
            </xbrli:divide>
        </xbrli:unit>
    </xbrl>
    """

@pytest.fixture
def sample_context_xml():
    """Provide sample XML with a context definition."""
    return """
    <xbrl xmlns:xbrli="http://www.xbrl.org/2001/instance">
        <xbrli:context id="ctx1">
            <xbrli:entity>
                <xbrli:identifier scheme="http://www.sec.gov/CIK">0000000001</xbrli:identifier>
            </xbrli:entity>
            <xbrli:period>
                <xbrli:instant>2024-01-01</xbrli:instant>
            </xbrli:period>
        </xbrli:context>
    </xbrl>
    """


def test_fact_parsing(processor, sample_fact_xml):
    """Test that facts are correctly parsed from XML."""
    root = etree.fromstring(sample_fact_xml)
    # Add test namespace
    processor.namespaces['test'] = 'http://test.namespace'
    # Add context for reference
    processor.contexts['ctx1'] = XBRLContext(
        id='ctx1',
        entity='test',
        instant=datetime.now()
    )

    processor._parse_facts(root)

    assert len(processor.facts) == 2
    numeric_fact = next(f for f in processor.facts if f.concept == 'test:Revenue')
    text_fact = next(f for f in processor.facts if f.concept == 'test:Description')

    assert numeric_fact.value == 1000.00
    assert text_fact.value == 'Test description'


def test_validation_missing_context(processor):
    """Test validation catches facts with missing context references."""
    processor.facts.append(XBRLFact(
        concept='test:Value',
        value=100,
        context_ref='missing_context',
        unit_ref='usd'
    ))

    errors = processor.validate()
    assert any('missing context' in error.lower() for error in errors)


def test_validation_missing_unit(processor):
    """Test validation catches numeric facts with missing unit references."""
    processor.contexts['ctx1'] = XBRLContext(
        id='ctx1',
        entity='test',
        instant=datetime.now()
    )

    processor.facts.append(XBRLFact(
        concept='test:Value',
        value=100,
        context_ref='ctx1',
        unit_ref='missing_unit'
    ))

    errors = processor.validate()
    assert any('missing unit' in error.lower() for error in errors)


def test_context_periods(processor):
    """Test different types of period handling in contexts."""
    instant_xml = """
    <xbrl xmlns:xbrli="http://www.xbrl.org/2001/instance">
        <xbrli:context id="ctx1">
            <xbrli:entity>
                <xbrli:identifier scheme="http://www.sec.gov/CIK">0000000001</xbrli:identifier>
            </xbrli:entity>
            <xbrli:period>
                <xbrli:instant>2024-01-01</xbrli:instant>
            </xbrli:period>
        </xbrli:context>
    </xbrl>
    """

    duration_xml = """
    <xbrl xmlns:xbrli="http://www.xbrl.org/2001/instance">
        <xbrli:context id="ctx2">
            <xbrli:entity>
                <xbrli:identifier scheme="http://www.sec.gov/CIK">0000000001</xbrli:identifier>
            </xbrli:entity>
            <xbrli:period>
                <xbrli:startDate>2024-01-01</xbrli:startDate>
                <xbrli:endDate>2024-12-31</xbrli:endDate>
            </xbrli:period>
        </xbrli:context>
    </xbrl>
    """

    root1 = etree.fromstring(instant_xml)
    root2 = etree.fromstring(duration_xml)

    processor._parse_contexts(root1)
    processor._parse_contexts(root2)

    assert processor.contexts['ctx1'].instant is not None
    assert processor.contexts['ctx2'].period_start is not None
    assert processor.contexts['ctx2'].period_end is not None


@pytest.mark.integration
def test_real_file_loading(processor, tmp_path):
    """Test loading a real XBRL file (Novartis example)."""
    # Get the path to the test directory
    test_dir = Path(__file__).parent
    novartis_file = test_dir.parent / 'Novartis-2002-11-15.xml'

    # Skip if files don't exist
    if not novartis_file.exists():
        pytest.skip(f"Novartis test files not found at {novartis_file}")

    processor.load_instance(novartis_file)

    # Add more detailed assertions to help diagnose issues
    assert len(processor.contexts) > 0, "No contexts were loaded"
    assert len(processor.units) > 0, "No units were loaded"
    assert len(processor.facts) > 0, "No facts were loaded"

    # Test specific known values from the Novartis file
    assert 'Group2001AsOf' in processor.contexts, "Expected context 'Group2001AsOf' not found"
    assert processor.contexts['Group2001AsOf'].entity.endswith('Novartis Group'), \
        "Incorrect entity for Group2001AsOf context"


def test_novartis_debug(processor):
    """Debug test for Novartis file loading."""
    test_dir = Path(__file__).parent
    novartis_file = test_dir.parent / 'Novartis-2002-11-15.xml'

    if not novartis_file.exists():
        pytest.skip(f"Novartis test files not found at {novartis_file}")

    # Load and parse manually to debug
    tree = etree.parse(str(novartis_file))
    root = tree.getroot()

    # Print namespaces for debugging
    print("\nNamespaces found in document:")
    for prefix, uri in root.nsmap.items():
        print(f"{prefix}: {uri}")

    # Find all context elements
    contexts = root.findall('.//xbrli:context', processor.namespaces)
    print(f"\nNumber of contexts found: {len(contexts)}")

    # Debug first context if any exist
    if contexts:
        first_context = contexts[0]
        print("\nFirst context structure:")
        print(etree.tostring(first_context, pretty_print=True).decode())

        # Try extracting entity
        entity = processor._extract_entity(first_context)
        print(f"\nExtracted entity: {entity}")

        # Try extracting period
        period_data = processor._extract_period(first_context)
        print(f"\nExtracted period data: {period_data}")
    else:
        print("\nNo contexts found - check XPath and namespaces")

    # Test namespace resolution
    print("\nTesting namespace resolution:")
    for prefix, uri in processor.namespaces.items():
        print(f"Looking for elements with namespace {prefix}")
        elements = root.findall(f'.//{{{uri}}}context')
        print(f"Found {len(elements)} elements")


def test_group_root_document(processor):
    """Test parsing XBRL document with group root element."""
    # Remove XML declaration and use simplified namespace
    sample_xml = """
    <group xmlns='http://www.xbrl.org/2001/instance'>
        <context id="ctx1">
            <entity>
                <identifier scheme="http://www.test.com">TestCompany</identifier>
            </entity>
            <period>
                <instant>2024-01-01</instant>
            </period>
        </context>
    </group>
    """
    root = etree.fromstring(sample_xml.strip())
    processor._parse_contexts(root)

    assert len(processor.contexts) > 0, "No contexts were loaded"
    assert "ctx1" in processor.contexts, "Expected context not found"
    assert processor.contexts["ctx1"].entity == "http://www.test.com:TestCompany"

    # Add additional test for the Novartis format
    novartis_xml = """
    <group xmlns='http://www.xbrl.org/2001/instance'>
        <numericContext id="testContext" precision="18" cwa="true">
            <entity>
                <identifier scheme="http://www.novartis.com/group">Novartis Group</identifier>
            </entity>
            <period>
                <instant>2001-12-31</instant>
            </period>
        </numericContext>
    </group>
    """
    root = etree.fromstring(novartis_xml.strip())
    processor.contexts.clear()  # Clear previous contexts
    processor._parse_contexts(root)

    assert len(processor.contexts) > 0, "No Novartis contexts were loaded"
    assert "testContext" in processor.contexts, "Expected Novartis context not found"