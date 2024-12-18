from decimal import Decimal
from typing import Dict, List, Set, Tuple, Optional, Union
from dataclasses import dataclass
from lxml import etree


@dataclass
class CalculationRelationship:
    parent: str  # Parent concept
    child: str  # Child concept
    weight: Decimal  # Usually 1 or -1
    order: int  # Processing order within calculation group
    role: str  # Extended role for grouping calculations


class CalculationValidator:
    def __init__(self):
        self.calc_relationships: Dict[str, List[CalculationRelationship]] = {}
        self.calculation_roles: Dict[str, str] = {}  # Role URI to description mapping
        self.namespaces = {
            'link': 'http://www.xbrl.org/2003/linkbase',
            'xlink': 'http://www.w3.org/1999/xlink',
            'xbrli': 'http://www.xbrl.org/2003/instance'
        }

    def load_calculation_linkbase(self, source: Union[str, etree._ElementTree]) -> None:
        """
        Load calculation relationships from a calculation linkbase.

        Args:
            source: Either a file path string or an already parsed etree._ElementTree
        """
        try:
            # Get the root element whether from file or tree
            if isinstance(source, str):
                tree = etree.parse(source)
                root = tree.getroot()
            elif isinstance(source, etree._ElementTree):
                root = source.getroot()
            else:
                raise ValueError(f"Unsupported source type: {type(source)}")

            # First load roles if defined
            for role_ref in root.findall('.//link:roleRef', self.namespaces):
                role_uri = role_ref.get('roleURI')
                if role_uri:
                    self.calculation_roles[role_uri] = role_ref.get(f"{{{self.namespaces['xlink']}}}label", role_uri)

            # Process each calculation link (grouped by role)
            for calc_link in root.findall('.//link:calculationLink', self.namespaces):
                role = calc_link.get(f"{{{self.namespaces['xlink']}}}role", "")

                # Build locator map for this calculation group
                locators = {}
                for loc in calc_link.findall('link:loc', self.namespaces):
                    label = loc.get(f"{{{self.namespaces['xlink']}}}label")
                    href = loc.get(f"{{{self.namespaces['xlink']}}}href")
                    if label and href:
                        concept = self._extract_concept_from_href(href)
                        locators[label] = concept

                # Process calculation arcs
                for arc in calc_link.findall('link:calculationArc', self.namespaces):
                    try:
                        weight = Decimal(arc.get('weight', '1.0'))
                        order = int(arc.get('order', '1'))
                        from_label = arc.get(f"{{{self.namespaces['xlink']}}}from")
                        to_label = arc.get(f"{{{self.namespaces['xlink']}}}to")

                        if from_label in locators and to_label in locators:
                            parent = locators[from_label]
                            child = locators[to_label]

                            relationship = CalculationRelationship(
                                parent=parent,
                                child=child,
                                weight=weight,
                                order=order,
                                role=role
                            )

                            if parent not in self.calc_relationships:
                                self.calc_relationships[parent] = []
                            self.calc_relationships[parent].append(relationship)

                    except (ValueError, KeyError) as e:
                        print(f"Warning: Error processing calculation arc: {e}")

        except Exception as e:
            print(f"Error loading calculation linkbase: {e}")
            raise

    def _extract_concept_from_href(self, href: str) -> str:
        """Extract concept name from href attribute."""
        if '#' in href:
            return href.split('#')[-1]
        return href

    def validate_calculations(self, facts: Dict[str, Dict[str, Decimal]]) -> List[str]:
        """
        Validate calculation relationships across all contexts.

        Args:
            facts: Dict mapping context_id to Dict of concept-value pairs
        """
        errors = []

        # Process each context separately
        for context_id, context_facts in facts.items():
            context_errors = self.validate_context_calculations(context_facts, context_id)
            errors.extend(context_errors)

        return errors

    def validate_context_calculations(self, facts: Dict[str, Decimal], context_id: str) -> List[str]:
        """Validate calculations for a single context."""
        errors = []
        processed = set()  # Track processed calculations to avoid cycles

        for parent_concept, relationships in self.calc_relationships.items():
            if parent_concept in facts and parent_concept not in processed:
                # Sort relationships by order
                sorted_rels = sorted(relationships, key=lambda r: r.order)

                expected_sum = Decimal('0')
                missing_children = []
                used_children = set()

                # Sum up all children according to their weights
                for rel in sorted_rels:
                    if rel.child in facts:
                        child_value = facts[rel.child]
                        expected_sum += child_value * rel.weight
                        used_children.add(rel.child)
                    else:
                        missing_children.append(rel.child)

                # Only validate if we have all required children
                if not missing_children:
                    parent_value = facts[parent_concept]
                    # Allow for small rounding differences (configurable threshold)
                    if abs(parent_value - expected_sum) > Decimal('0.01'):
                        role_desc = self.calculation_roles.get(relationships[0].role, "default")
                        errors.append(
                            f"Calculation error in {parent_concept} (role: {role_desc}, context: {context_id}): "
                            f"Expected {expected_sum}, got {parent_value}. "
                            f"Children used: {', '.join(sorted(used_children))}"
                        )
                else:
                    errors.append(
                        f"Missing children for calculation of {parent_concept} "
                        f"(context: {context_id}): {', '.join(missing_children)}"
                    )

                processed.add(parent_concept)

        return errors

    def get_calculation_network(self, role: Optional[str] = None) -> Dict[str, List[Tuple[str, Decimal]]]:
        """
        Get a hierarchical view of calculation relationships, optionally filtered by role.

        Args:
            role: Optional role URI to filter relationships

        Returns:
            Dictionary mapping parent concepts to list of (child_concept, weight) tuples
        """
        network: Dict[str, List[Tuple[str, Decimal]]] = {}

        for parent, relationships in self.calc_relationships.items():
            if role is None or any(r.role == role for r in relationships):
                filtered_rels = [r for r in relationships if role is None or r.role == role]
                network[parent] = [(r.child, r.weight) for r in
                                   sorted(filtered_rels, key=lambda x: x.order)]

        return network

    def get_all_calculation_networks(self) -> Dict[str, Dict[str, List[Tuple[str, Decimal]]]]:
        """
        Get all calculation networks organized by role.

        Returns:
            Dictionary mapping roles to their calculation networks
        """
        networks: Dict[str, Dict[str, List[Tuple[str, Decimal]]]] = {}

        # Group relationships by role first
        role_relationships: Dict[str, List[CalculationRelationship]] = {}
        for rels in self.calc_relationships.values():
            for rel in rels:
                if rel.role not in role_relationships:
                    role_relationships[rel.role] = []
                role_relationships[rel.role].append(rel)

        # Create network for each role
        for role, rels in role_relationships.items():
            role_network: Dict[str, List[Tuple[str, Decimal]]] = {}
            for rel in rels:
                if rel.parent not in role_network:
                    role_network[rel.parent] = []
                role_network[rel.parent].append((rel.child, rel.weight))
            networks[role] = role_network

        return networks

    def get_calculation_roots(self, role: Optional[str] = None) -> Set[str]:
        """Get concepts that appear only as parents (calculation roots) for a given role."""
        all_parents = {parent for parent, rels in self.calc_relationships.items()
                       if role is None or any(r.role == role for r in rels)}
        all_children = {rel.child for rels in self.calc_relationships.values()
                        for rel in rels if role is None or rel.role == role}
        return all_parents - all_children