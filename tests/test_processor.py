import pytest
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from lxml import etree
from processor import XBRLProcessor, XBRLContext, XBRLUnit, XBRLFact


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
def test_real_file_loading(processor):
    """Test comprehensive real-world XBRL processing."""
    test_dir = Path(__file__).parent
    novartis_file = test_dir.parent / 'Novartis-2002-11-15.xml'

    if not novartis_file.exists():
        pytest.skip(f"Novartis test files not found at {novartis_file}")

    processor.load_instance(novartis_file)

    # Test context loading
    assert len(processor.contexts) > 0, "No contexts were loaded"
    assert 'Group2001AsOf' in processor.contexts, "Expected context not found"
    assert processor.contexts['Group2001AsOf'].entity.endswith('Novartis Group')

    # Test unit loading
    assert len(processor.units) > 0, "No units were loaded"
    chf_units = [u for u in processor.units.values() if any('CHF' in m for m in u.measures)]
    assert len(chf_units) > 0, "Expected CHF unit not found"

    # Test fact loading
    assert len(processor.facts) > 0, "No facts were loaded"

    # Test specific fact values
    revenue_facts = [f for f in processor.facts if 'Revenue' in f.concept]
    assert len(revenue_facts) > 0, "No revenue facts found"
    assert all(isinstance(f.value, (int, float)) for f in revenue_facts)

    # Validate full dataset
    errors = processor.validate()
    assert len(errors) == 0, f"Validation errors found:\n" + "\n".join(errors)