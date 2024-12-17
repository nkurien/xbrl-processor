# xbrl_processor.py
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from pathlib import Path
from datetime import datetime
from lxml import etree
import pandas as pd
import json
from decimal import Decimal, InvalidOperation
import re


@dataclass
class XBRLFile:
    path: Path
    file_type: str
    namespaces: Dict[str, str]
    root_element: str
    role_refs: Dict[str, str] = field(default_factory=dict)


class XBRLFolderProcessor:
    def __init__(self):
        self.base_processor = XBRLProcessor()  # Default to standard processor
        self.discovered_files = {}
        self._namespace_patterns = {}

    def _analyze_xml_file(self, file_path: Path) -> Optional[XBRLFile]:
        """Analyze XML file structure to determine its type based on content."""
        try:
            # Add more detailed error handling and debugging
            print(f"Debug: Reading file {file_path}")
            parser = etree.XMLParser(recover=True)  # More lenient parsing
            tree = etree.parse(str(file_path), parser=parser)
            root = tree.getroot()

            # Get namespaces from root
            namespaces = {k if k is not None else '': v
                         for k, v in root.nsmap.items()}

            root_element = etree.QName(root).localname
            roles = self._extract_roles(root)

            # Identify file type based on XML structure
            file_type = self._determine_file_type(root, namespaces, roles)

            if file_type:
                return XBRLFile(
                    path=file_path,
                    file_type=file_type,
                    namespaces=namespaces,
                    root_element=root_element,
                    role_refs=roles
                )

            return None

        except Exception as e:
            print(f"Warning: Error analyzing {file_path}: {str(e)}")
            return None

    def _extract_roles(self, root: etree.Element) -> Dict[str, str]:
        """Extract role references and definitions from the XML."""
        roles = {}
        for elem in root.iter():
            role = elem.get('role', '')
            arc_role = elem.get('arcrole', '')
            if role:
                roles[role] = elem.tag
            if arc_role:
                roles[arc_role] = elem.tag
        return roles

    def _determine_file_type(self, root: etree.Element,
                             namespaces: Dict[str, str],
                             roles: Dict[str, str]) -> Optional[str]:
        """Determine file type based on XML structure and content analysis."""
        root_tag = etree.QName(root.tag).localname
        ns_values = set(namespaces.values())

        # Debug namespace information
        print(f"Debug: Root tag: {root_tag}")
        print(f"Debug: Namespaces: {namespaces}")

        # Check for iXBRL by looking for specific namespaces
        if 'http://www.xbrl.org/2013/inlineXBRL' in ns_values:
            print("Debug: Found iXBRL namespace")
            return 'ixbrl'

        # Check for iXBRL based on root element
        if root_tag.lower() == 'html' and any('inline' in ns.lower() for ns in ns_values):
            print("Debug: Found iXBRL based on HTML root and inline namespace")
            return 'ixbrl'

        # Existing detection logic...
        if root_tag in {'xbrl', 'group'}:
            if any('instance' in ns.lower() for ns in ns_values):
                return 'instance'

        if root_tag == 'schema':
            return 'schema'

        if root_tag == 'linkbase':
            return self._analyze_linkbase(root, roles)

        return None

    def _analyze_linkbase(self, root: etree.Element,
                          roles: Dict[str, str]) -> str:
        """Analyze linkbase content to determine specific type."""
        # Look for specific link elements
        for element in root.iter():
            local_name = etree.QName(element.tag).localname.lower()

            # Check element name patterns
            if 'calculation' in local_name:
                return 'calculation'
            elif 'presentation' in local_name:
                return 'presentation'
            elif 'label' in local_name:
                return 'label'
            elif 'reference' in local_name:
                return 'reference'

            # Check roles
            role = element.get('role', '').lower()
            if role:
                if 'calculation' in role:
                    return 'calculation'
                elif 'presentation' in role:
                    return 'presentation'
                elif 'label' in role:
                    return 'label'
                elif 'reference' in role:
                    return 'reference'

        return 'linkbase'

    def _discover_files(self, folder_path: Path) -> None:
        """Discover and analyze all XML files in the folder."""
        self.discovered_files.clear()

        # Update file patterns to include .htm files
        xml_files = list(folder_path.glob('*.xml')) + \
                   list(folder_path.glob('*.xsd')) + \
                   list(folder_path.glob('*.htm'))  # Add .htm files

        # First pass: collect namespace patterns
        for file_path in xml_files:
            if file_path.is_file():
                print(f"\nDebug: Analyzing {file_path.name}")
                xbrl_file = self._analyze_xml_file(file_path)
                if xbrl_file:
                    self.discovered_files[file_path.name] = xbrl_file

        print("\nDebug: File analysis results:")
        for name, file in self.discovered_files.items():
            ns_names = [f"{k} -> {v.split('/')[-1]}"
                        for k, v in file.namespaces.items()]
            print(f"  {name}:")
            print(f"    Type: {file.file_type}")
            print(f"    Root: {file.root_element}")
            print(f"    Namespaces: {', '.join(ns_names)}")
            if file.role_refs:
                print(f"    Roles: {', '.join(file.role_refs.keys())}")

    def process_folder(self, folder_path: Path) -> None:
        """Process all XBRL files in a folder structure."""
        if not folder_path.is_dir():
            raise ValueError(f"Path {folder_path} is not a directory")

        self._discover_files(folder_path)

        # Find instance or iXBRL documents
        instance_files = [f for f in self.discovered_files.values()
                          if f.file_type in ('instance', 'ixbrl')]

        if not instance_files:
            raise ValueError(f"No XBRL or iXBRL instance document found in {folder_path}")

        # Process main instance document first
        main_instance = instance_files[0]
        print(f"\nDebug: Loading main instance: {main_instance.path}")

        # Create appropriate processor based on file type
        if main_instance.file_type == 'ixbrl':
            self.base_processor = iXBRLProcessor()
            self.base_processor.load_ixbrl_instance(main_instance.path)
        else:
            self.base_processor = XBRLProcessor()
            self.base_processor.load_instance(main_instance.path)

        # Process schema files
        schema_files = [f for f in self.discovered_files.values()
                        if f.file_type == 'schema']
        for schema in schema_files:
            try:
                print(f"Debug: Loading schema: {schema.path}")
                self.base_processor.load_taxonomy(schema.path)
            except Exception as e:
                print(f"Warning: Error loading schema {schema.path}: {e}")

        # Process calculation files
        calc_files = [f for f in self.discovered_files.values()
                      if f.file_type == 'calculation']
        for calc in calc_files:
            try:
                print(f"Debug: Loading calculation: {calc.path}")
                self.base_processor.load_calculation(calc.path)
            except Exception as e:
                print(f"Warning: Error loading calculation {calc.path}: {e}")

    @property
    def contexts(self):
        """Access contexts from the base processor."""
        return self.base_processor.contexts if self.base_processor else {}

    @property
    def units(self):
        """Access units from the base processor."""
        return self.base_processor.units if self.base_processor else {}

    @property
    def facts(self):
        """Access facts from the base processor."""
        return self.base_processor.facts if self.base_processor else []

    def validate(self) -> List[str]:
        return self.base_processor.validate()

    def export_to_json(self, output_path: Path) -> None:
        self.base_processor.export_to_json(output_path)

    def export_to_csv(self, output_path: Path) -> None:
        self.base_processor.export_to_csv(output_path)

@dataclass
class XBRLContext:
    id: str
    entity: str
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    instant: Optional[datetime] = None
    scenario: Optional[Dict[str, Any]] = None
    
    @property
    def is_duration(self) -> bool:
        return self.period_start is not None and self.period_end is not None

    @property
    def is_instant(self) -> bool:
        return self.instant is not None

@dataclass
class XBRLUnit:
    id: str
    measures: List[str]  # e.g., ['iso4217:USD'] or ['xbrli:pure']
    divide: bool = False  # True if it's a divide relationship (e.g., shares/shares)
    numerator: List[str] = field(default_factory=list)
    denominator: List[str] = field(default_factory=list)

@dataclass
class XBRLFact:
    concept: str
    value: Any
    context_ref: str
    unit_ref: Optional[str] = None
    decimals: Optional[int] = None
    precision: Optional[int] = None

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