from processor import  XBRLProcessor
from models import XBRLFile
from inline_processor import iXBRLProcessor
from lxml import etree
from pathlib import Path
from typing import Dict, List, Optional, Any


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