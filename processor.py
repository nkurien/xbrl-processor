# xbrl_processor.py
from models import XBRLContext, XBRLUnit, XBRLFact
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime
from lxml import etree
import pandas as pd
import json


class XBRLProcessor:
    def __init__(self):
        self.namespaces = {
            'xbrli': 'http://www.xbrl.org/2001/instance',
            'link': 'http://www.xbrl.org/2001/XLink/xbrllinkbase',
            'xlink': 'http://www.w3.org/1999/xlink',
            'iso4217': 'http://www.xbrl.org/2003/iso4217',
            'iascf-pfs': 'http://www.xbrl.org/taxonomy/int/fr/ias/ci/pfs/2002-11-15'
        }
        self.contexts: Dict[str, XBRLContext] = {}
        self.units: Dict[str, XBRLUnit] = {}
        self.facts: List[XBRLFact] = []
        self.schema_refs: List[str] = []
        self.taxonomy_tree = None
        self.calculation_tree = None

    def load_instance(self, instance_path: Path) -> None:
        """Load and parse the main XBRL instance document."""
        try:
            tree = etree.parse(str(instance_path))
            root = tree.getroot()

            # Update namespaces from the document
            for prefix, uri in root.nsmap.items():
                if prefix is not None:  # Skip default namespace
                    self.namespaces[prefix] = uri

            # Handle both group and xbrl root elements
            if root.tag.endswith('group'):
                # If root is group, use it directly
                process_root = root
            else:
                # Otherwise look for group element
                group = root.find('.//group')
                process_root = group if group is not None else root

            # Parse the main components
            self._parse_contexts(process_root)
            if not self.contexts:
                # Debug output
                print("\nDebug information:")
                print("Root tag:", root.tag)
                print("Available elements:", [elem.tag for elem in root.iter()][:10])
                print("Searching with xpath:", root.xpath('.//xbrli:context', namespaces=self.namespaces))

            self._parse_units(process_root)
            self._parse_facts(process_root)

        except Exception as e:
            raise ValueError(f"Error parsing XBRL instance: {str(e)}")

    def load_taxonomy(self, taxonomy_path: Path) -> None:
        """Load and parse the taxonomy schema."""
        try:
            self.taxonomy_tree = etree.parse(str(taxonomy_path))
            # Add any taxonomy-specific namespaces
            for prefix, uri in self.taxonomy_tree.getroot().nsmap.items():
                if prefix and uri and prefix not in self.namespaces:
                    self.namespaces[prefix] = uri

        except Exception as e:
            raise ValueError(f"Error loading taxonomy: {str(e)}")

    def load_calculation(self, calculation_path: Path) -> None:
        """Load and parse the calculation linkbase."""
        try:
            self.calculation_tree = etree.parse(str(calculation_path))
            # Process calculation relationships here
            self._process_calculation_links()
            
        except Exception as e:
            raise ValueError(f"Error loading calculation linkbase: {str(e)}")

    def _parse_numeric_attribute(self, value: Optional[str]) -> Optional[int]:
        """Parse numeric attributes like decimals and precision."""
        if value is None:
            return None

        try:
            # Handle special values defined in the XBRL specification
            if value == 'INF':
                return float('inf')
            return int(value)
        except ValueError:
            return None

    def _parse_contexts(self, root: etree.Element) -> None:
        """Parse context elements from the instance document."""
        # List to collect all found contexts
        contexts = []

        # Try standard context elements first
        contexts.extend(root.findall('.//xbrli:context', self.namespaces))

        # Try numeric context elements
        contexts.extend(root.findall('.//numericContext', {'': 'http://www.xbrl.org/2001/instance'}))

        # Try with default namespace
        if not contexts:
            ns = {'': 'http://www.xbrl.org/2001/instance'}
            contexts.extend(root.findall('.//context', ns))

        # Try xpath with local-name for both types
        if not contexts:
            contexts.extend(root.xpath('.//*[local-name()="context" or local-name()="numericContext"]'))

        print(f"Debug: Found {len(contexts)} contexts")
        if contexts:
            print(f"Debug: First context: {etree.tostring(contexts[0])}")

        for context in contexts:
            context_id = context.get('id')
            if not context_id:
                continue

            entity = self._extract_entity(context)
            if entity:  # Only process if we got a valid entity
                period_data = self._extract_period(context)
                scenario = self._extract_scenario(context)

                self.contexts[context_id] = XBRLContext(
                    id=context_id,
                    entity=entity,
                    scenario=scenario,
                    **period_data
                )

    def _extract_entity(self, context: etree.Element) -> Optional[str]:
        """Extract entity identifier from context."""
        # Try different namespace patterns for identifier element
        identifier = None

        # Pattern 1: Using xbrli namespace
        identifier = context.find('.//xbrli:identifier', self.namespaces)

        # Pattern 2: Using default namespace
        if identifier is None:
            identifier = context.find('.//identifier', {'': 'http://www.xbrl.org/2001/instance'})

        # Pattern 3: Using local-name
        if identifier is None:
            matches = context.xpath('.//*[local-name()="identifier"]')
            if matches:
                identifier = matches[0]

        if identifier is not None and identifier.text:
            scheme = identifier.get('scheme', '')
            entity_text = identifier.text.strip()
            return f"{scheme}:{entity_text}" if scheme else entity_text
        return None

    def register_namespace(self, prefix: str, uri: str) -> None:
        """Register a new namespace mapping."""
        self.namespaces[prefix] = uri
        # Register with empty prefix for default namespace if needed
        if uri == "http://www.xbrl.org/2001/instance":
            self.namespaces[''] = uri
        etree.register_namespace(prefix, uri)
    
    def _extract_entity(self, context: etree.Element) -> str:
        """Extract entity identifier from context."""
        entity_elem = context.find('.//xbrli:entity/xbrli:identifier', self.namespaces)
        if entity_elem is not None:
            scheme = entity_elem.get('scheme', '')
            return f"{scheme}:{entity_elem.text}" if entity_elem.text else ''
        return ''
    
    def _extract_period(self, context: etree.Element) -> dict:
        """Extract period information from context."""
        period = context.find('.//xbrli:period', self.namespaces)
        if period is None:
            return {}
            
        instant = period.find('xbrli:instant', self.namespaces)
        if instant is not None:
            return {'instant': self._parse_date(instant.text)}
            
        start = period.find('xbrli:startDate', self.namespaces)
        end = period.find('xbrli:endDate', self.namespaces)
        return {
            'period_start': self._parse_date(start.text) if start is not None else None,
            'period_end': self._parse_date(end.text) if end is not None else None
        }

    def _parse_units(self, root: etree.Element) -> None:
        """Parse unit definitions from the instance document."""
        self.units = {}
        all_units = []

        # Try standard units
        ns = {'xbrli': 'http://www.xbrl.org/2001/instance'}
        standalone_units = root.findall('.//xbrli:unit', ns)
        if standalone_units:
            all_units.extend(standalone_units)

        # Try finding numericContext elements and extract their units
        for context in root.findall('.//numericContext', {'': 'http://www.xbrl.org/2001/instance'}):
            context_id = context.get('id')
            if not context_id:
                continue

            # Find unit within this context
            unit = context.find('./unit', {'': 'http://www.xbrl.org/2001/instance'})
            if unit is not None:
                # Store reference to process this unit with its context ID
                all_units.append((unit, context_id))

        print(f"Debug: Found {len(all_units)} units")

        # Process all found units
        for unit_item in all_units:
            if isinstance(unit_item, tuple):
                unit, context_id = unit_item
                self._process_unit_element(unit, context_id)
            else:
                self._process_unit_element(unit_item)

    def _process_unit_element(self, unit: etree.Element, override_id: str = None) -> None:
        """Process a single unit element."""
        unit_id = override_id or unit.get('id')
        if not unit_id:
            return

        measures = []
        numerator = []
        denominator = []
        divide = False

        # Try finding measure elements in the default instance namespace
        for measure in unit.findall('./measure', {'': 'http://www.xbrl.org/2001/instance'}):
            if measure.text:
                measures.append(measure.text.strip())

        # If no measures found, try with xbrli namespace
        if not measures:
            for measure in unit.findall('.//xbrli:measure', self.namespaces):
                if measure.text:
                    measures.append(measure.text.strip())

        # Handle divide relationships
        divide_elem = unit.find('./divide', {'': 'http://www.xbrl.org/2001/instance'})
        if divide_elem is not None:
            divide = True
            for num_measure in divide_elem.findall('.//numerator//measure', {'': 'http://www.xbrl.org/2001/instance'}):
                if num_measure.text:
                    numerator.append(num_measure.text.strip())
            for den_measure in divide_elem.findall('.//denominator//measure',
                                                   {'': 'http://www.xbrl.org/2001/instance'}):
                if den_measure.text:
                    denominator.append(den_measure.text.strip())

        if measures or numerator:  # Only create unit if we found any measures
            self.units[unit_id] = XBRLUnit(
                id=unit_id,
                measures=measures,
                divide=divide,
                numerator=numerator,
                denominator=denominator
            )

    def _extract_scenario(self, context: etree.Element) -> Optional[Dict[str, Any]]:
        """Extract scenario information from context."""
        scenario = context.find('.//xbrli:scenario', self.namespaces)
        if scenario is None:
            return None
            
        return {'segments': [self._element_to_dict(child) for child in scenario]}

    def _element_to_dict(self, element: etree.Element) -> dict:
        """Convert an XML element to a dictionary representation."""
        # Get the local name without namespace
        tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag

        result = {}
        # Add text value if present
        if element.text and element.text.strip():
            result[tag] = element.text.strip()
        # Add attributes if present
        if element.attrib:
            for attr, value in element.attrib.items():
                attr_name = attr.split('}')[-1] if '}' in attr else attr
                result[f"{tag}@{attr_name}"] = value
        # Add children recursively
        for child in element:
            child_dict = self._element_to_dict(child)
            result.update(child_dict)
        return result

    def _parse_facts(self, root: etree.Element) -> None:
        """Extract facts from the instance document."""
        # Clear existing facts to prevent duplicates
        self.facts = []

        # Debug all namespaces in document
        print("Debug: Available namespaces:", root.nsmap)

        # Find facts from all relevant namespaces
        facts_found = []

        # Add known financial reporting namespaces
        self.namespaces.update({
            'iascf-pfs': 'http://www.xbrl.org/taxonomy/int/fr/ias/ci/pfs/2002-11-15',
            'novartis': 'http://www.xbrl.org/taxonomy/int/fr/ias/pfs/2002-11-15/Novartis-2002-11-15'
        })

        # Find all elements that could be facts
        for child in root.iter():
            # Skip elements in instance namespace
            if child.tag.startswith(f'{{{self.namespaces["xbrli"]}}}'):
                continue

            # Get context reference - try both styles
            context_ref = child.get('contextRef') or child.get('numericContext')
            if not context_ref:
                continue

            # Only process if we have the context
            if context_ref in self.contexts:
                # Extract numeric attributes
                decimals = self._parse_numeric_attribute(child.get('decimals'))
                precision = self._parse_numeric_attribute(child.get('precision'))

                # Get unit reference either from attribute or numeric context
                unit_ref = child.get('unitRef')
                if not unit_ref and context_ref in self.contexts:
                    # If numeric context has an embedded unit, use the context ID as the unit reference
                    # since we've already extracted these units in _parse_units
                    if self.contexts[context_ref] and context_ref in self.units:
                        unit_ref = context_ref

                # Extract value
                value = self._extract_fact_value(child)
                if value is not None:
                    fact = XBRLFact(
                        concept=self._get_concept_name(child),
                        value=value,
                        context_ref=context_ref,
                        unit_ref=unit_ref,
                        decimals=decimals,
                        precision=precision
                    )
                    facts_found.append(fact)

        print(f"Debug: Found {len(facts_found)} facts")
        if facts_found:
            print(f"Debug: First fact: {facts_found[0]}")

        self.facts.extend(facts_found)

    def _parse_date(self, date_str: str) -> datetime:
        """Parse XBRL date string to datetime object.

        Args:
            date_str: A date string in XBRL format (YYYY-MM-DD or YYYY-MM-DDThh:mm:ss)

        Returns:
            datetime: The parsed datetime object

        Examples:
            >>> processor._parse_date("2024-01-01")
            datetime.datetime(2024, 1, 1, 0, 0)
            >>> processor._parse_date("2024-01-01T12:00:00")
            datetime.datetime(2024, 1, 1, 12, 0)
        """
        if not date_str:
            return None

        date_str = date_str.strip()

        try:
            # Try simple date format first
            if 'T' not in date_str:
                return datetime.strptime(date_str, '%Y-%m-%d')
            # Try date+time format if needed
            return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
        except ValueError as e:
            raise ValueError(f"Unable to parse date '{date_str}': {str(e)}")

    def _get_concept_name(self, elem: etree.Element) -> str:
        """Get the concept name including namespace prefix."""
        tag = elem.tag
        if tag.startswith('{'):
            # Extract namespace and localname from Clark notation
            ns_uri = tag[1:tag.index('}')]
            localname = tag[tag.index('}') + 1:]

            # Find prefix for this namespace
            prefix = None
            for pre, uri in self.namespaces.items():
                if uri == ns_uri:
                    prefix = pre
                    break

            if prefix:
                return f"{prefix}:{localname}"

        # Fallback to local name only
        return tag.split('}')[-1]

    def _extract_fact_value(self, elem: etree.Element) -> Any:
        """Extract and type-convert fact values."""
        if elem.text is None:
            return None

        value = elem.text.strip()
        if not value:
            return None

        # Check for special attributes
        sign = elem.get('sign', '')
        if sign == '-':
            value = f'-{value}'

        # Try numeric conversion
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except ValueError:
            return value

    def _process_calculation_links(self) -> None:
        """Process calculation relationships from the calculation linkbase."""
        if self.calculation_tree is None:
            return
            
        # Implementation will go here - we'll add this in the next iteration
        pass

    def validate(self) -> List[str]:
        """Perform validation checks."""
        errors = []

        # Context reference validation
        for fact in self.facts:
            if fact.context_ref not in self.contexts:
                errors.append(
                    f"Fact {fact.concept} references missing context {fact.context_ref}"
                )

            # Unit validation for numeric facts
            if isinstance(fact.value, (int, float)):
                if not fact.unit_ref:
                    errors.append(
                        f"Numeric fact {fact.concept} missing required unit reference"
                    )
                elif fact.unit_ref not in self.units:
                    errors.append(
                        f"Fact {fact.concept} references missing unit {fact.unit_ref}"
                    )
            else:
                # Non-numeric facts should not have unit references
                if fact.unit_ref:
                    errors.append(
                        f"Non-numeric fact {fact.concept} should not have unit reference"
                    )

        return errors

    def to_dict(self) -> dict:
        """Convert the parsed XBRL data to a dictionary format."""
        return {
            'contexts': {k: vars(v) for k, v in self.contexts.items()},
            'units': {k: vars(v) for k, v in self.units.items()},
            'facts': [vars(f) for f in self.facts]
        }

    def export_to_json(self, output_path: Path) -> None:
        """Export the parsed data to JSON format."""
        data = self.to_dict()
        with output_path.open('w') as f:
            json.dump(data, f, indent=2, default=str)

    def export_to_csv(self, output_path: Path) -> None:
        """Export facts to CSV format."""
        rows = []
        for fact in self.facts:
            context = self.contexts[fact.context_ref]
            row = {
                'concept': fact.concept,
                'value': fact.value,
                'context_id': fact.context_ref,
                'unit': self.units[fact.unit_ref].measures[0] if fact.unit_ref else '',
                'entity': context.entity,
                'period_start': context.period_start,
                'period_end': context.period_end,
                'instant': context.instant
            }
            rows.append(row)
        
        df = pd.DataFrame(rows)
        df.to_csv(output_path, index=False)


