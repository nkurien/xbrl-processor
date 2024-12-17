from processor import XBRLProcessor
from models import XBRLContext, XBRLFact
from typing import List, Optional
from pathlib import Path
from lxml import etree
from decimal import Decimal, InvalidOperation


class iXBRLProcessor(XBRLProcessor):
    """Extension of XBRLProcessor to handle Inline XBRL (iXBRL) documents."""

    def __init__(self):
        super().__init__()
        self.namespaces.update({
            'ix': 'http://www.xbrl.org/2013/inlineXBRL',
            'ixt': 'http://www.xbrl.org/inlineXBRL/transformation/2020-02-12',
            'ixt-sec': 'http://www.sec.gov/inlineXBRL/transformation/2015-08-31',
            'html': 'http://www.w3.org/1999/xhtml'  # Add HTML namespace with explicit prefix
        })

    def load_ixbrl_instance(self, instance_path: Path) -> None:
        """Load and parse an Inline XBRL (iXBRL) document."""
        try:
            print("\nDebug: Starting iXBRL parsing")
            tree = etree.parse(str(instance_path))
            root = tree.getroot()

            # Update namespaces from the document
            self.namespaces.update(root.nsmap)

            # First find the hidden section which often contains contexts and units
            hidden = root.find('.//ix:hidden', self.namespaces)
            if hidden is not None:
                print("Debug: Found hidden section")
                self._parse_hidden_section(hidden)

            # If no contexts found in hidden section, look in the main document
            if not self.contexts:
                print("Debug: Looking for contexts in main document")
                self._parse_contexts(root)

            # Same for units
            if not self.units:
                print("Debug: Looking for units in main document")
                self._parse_units(root)

            # Parse facts
            print("\nDebug: Parsing facts")
            self._parse_ixbrl_facts(root)

            print(f"\nDebug: Parsing complete:")
            print(f"- Contexts: {len(self.contexts)}")
            print(f"- Units: {len(self.units)}")
            print(f"- Facts: {len(self.facts)}")

            # Print sample of what was found
            if self.facts:
                print("\nDebug: Sample facts:")
                for fact in self.facts[:3]:
                    print(f"- {fact.concept}: {fact.value}")

        except Exception as e:
            print(f"Error parsing iXBRL instance: {str(e)}")
            raise

    def _parse_hidden_section(self, hidden_elem: etree.Element) -> None:
        """Parse the hidden section of an iXBRL document."""
        print("\nDebug: Processing hidden section")

        # Process hidden contexts
        contexts = hidden_elem.findall('.//xbrli:context', self.namespaces)
        print(f"Debug: Found {len(contexts)} contexts in hidden section")
        for context in contexts:
            ctx_id = context.get('id')
            if ctx_id:
                entity = self._extract_entity(context)
                period_data = self._extract_period(context)
                scenario = self._extract_scenario(context)

                self.contexts[ctx_id] = XBRLContext(
                    id=ctx_id,
                    entity=entity,
                    scenario=scenario,
                    **period_data
                )

        # Process hidden units
        units = hidden_elem.findall('.//xbrli:unit', self.namespaces)
        print(f"Debug: Found {len(units)} units in hidden section")
        for unit in units:
            self._process_unit_element(unit)

    def _parse_ixbrl_facts(self, root: etree.Element) -> List[XBRLFact]:
        """Extract facts from iXBRL elements."""
        facts = []

        # Store the original facts list
        original_facts = self.facts
        self.facts = []

        try:
            # Find all types of facts
            for fact_type in ['nonFraction', 'nonNumeric', 'fraction']:
                # Try with namespace first
                elements = root.findall(f'.//ix:{fact_type}', self.namespaces)

                # If no elements found, try without namespace
                if not elements:
                    elements = root.findall(f'.//{fact_type}')

                print(f"Debug: Found {len(elements)} {fact_type} facts")

                for elem in elements:
                    fact = self._process_ixbrl_fact(elem)
                    if fact is not None:
                        facts.append(fact)
                        self.facts.append(fact)

            return facts

        except Exception as e:
            print(f"Error parsing iXBRL facts: {str(e)}")
            self.facts = original_facts  # Restore original facts on error
            return []  # Return empty list instead of None on error

    def _process_ixbrl_fact(self, elem: etree.Element) -> Optional[XBRLFact]:
        """Process a single iXBRL fact element."""
        try:
            # Get required attributes
            concept = elem.get('name')
            context_ref = elem.get('contextRef')

            if not (concept and context_ref):
                return None

            # Get optional attributes
            unit_ref = elem.get('unitRef')
            format = elem.get('format')
            scale = elem.get('scale')
            decimals = self._parse_numeric_attribute(elem.get('decimals'))
            precision = self._parse_numeric_attribute(elem.get('precision'))

            # Get the text value
            value = self._get_element_text(elem)

            # Apply transformations if specified
            if format:
                value = self._apply_transform(value, format)

            # Apply scaling if specified
            if scale and value:
                try:
                    value = self._apply_scaling(value, scale)
                except (ValueError, InvalidOperation):
                    print(f"Warning: Failed to apply scaling {scale} to value {value}")

            return XBRLFact(
                concept=concept,
                value=value,
                context_ref=context_ref,
                unit_ref=unit_ref,
                decimals=decimals,
                precision=precision
            )

        except Exception as e:
            print(f"Warning: Error processing fact {elem.get('name', 'unknown')}: {e}")
            return None

    def _apply_scaling(self, value: str, scale: str) -> str:
        """
        Apply scaling factor to numeric values using Decimal for precise calculations.
        """
        # Dictionary for common number words
        number_words = {
            'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
            'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
            'ten': '10'
        }

        try:
            # Handle special characters and empty values
            value = value.strip().lower()
            if not value or value in ['—', '–', '-', 'n/a']:
                return '0'

            # Convert number words to digits
            if value in number_words:
                value = number_words[value]

            # Remove commas and other formatting
            clean_value = value.replace(',', '')
            decimal_value = Decimal(clean_value)
            scale_factor = int(scale)

            scaled_value = decimal_value * Decimal(10) ** scale_factor
            return str(scaled_value.normalize())

        except (ValueError, InvalidOperation) as e:
            # Only print warning for values that aren't intentionally empty
            if value not in ['—', '–', '-', 'n/a'] and value not in number_words:
                print(f"Warning: Scaling error for value {value} with scale {scale}: {str(e)}")
            return value

    def _get_element_text(self, elem: etree.Element) -> str:
        """Get all text content from an element, handling nested elements."""
        result = []
        if elem.text:
            result.append(elem.text.strip())

        for child in elem:
            if child.tail:
                result.append(child.tail.strip())
            # If the child has its own text, process it too
            child_text = self._get_element_text(child)
            if child_text:
                result.append(child_text)

        return ' '.join(filter(None, result))

    def _apply_transform(self, value: str, format: str) -> str:
        """Apply iXBRL transformation rules to the value."""
        if not value or not format:
            return value

        # Strip whitespace first
        value = value.strip()

        # Handle number formats
        if format == 'ixt:numdotdecimal':
            # Format: 1,234.56 -> 1234.56
            # Remove any currency symbols first
            value = value.strip('$€£¥')
            # Remove any commas used as thousand separators
            value = value.replace(',', '')

        elif format == 'ixt:numcommadot':
            # Format: 1.234,56 -> 1234.56
            # Remove currency symbols
            value = value.strip('$€£¥')
            # First remove dots (thousand separators)
            value = value.replace('.', '')
            # Then replace comma with dot for decimal
            value = value.replace(',', '.')

        # Handle parenthetical negatives: (123) -> -123
        if value.startswith('(') and value.endswith(')'):
            value = '-' + value[1:-1]

        # Handle percentages: remove % and convert if needed
        if value.endswith('%'):
            value = value[:-1]
            # Optionally convert to decimal: 12.5% -> 0.125
            # Commenting out since your test expects to keep as-is
            # value = str(float(value) / 100)

        # Strip any remaining whitespace
        value = value.strip()

        return value

    def _parse_units(self, root: etree.Element) -> None:
        """Override to handle both standard and iXBRL units."""
        # Try finding units with explicit namespace
        units = root.findall('.//xbrli:unit', self.namespaces)

        if not units:
            # Try alternate approaches
            for ns in ['', 'http://www.xbrl.org/2003/instance']:
                units = root.findall(f'.//{{{ns}}}unit')
                if units:
                    break

        print(f"Debug: Found {len(units)} units")
        for unit in units:
            self._process_unit_element(unit)