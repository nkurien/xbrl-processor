from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from lxml import etree
from datetime import datetime
from decimal import Decimal
from pathlib import Path


@dataclass
class ValidationResult:
    """Represents the result of a validation check."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]


class TaxonomyValidator:
    """Handles comprehensive XBRL taxonomy validation."""

    def __init__(self):
        self.taxonomies: Dict[str, etree.XMLSchema] = {}
        self.concept_info: Dict[str, Dict] = {}  # Cache for concept definitions
        self.allowed_types = {
            'monetaryItemType': self._validate_monetary,
            'stringItemType': self._validate_string,
            'decimalItemType': self._validate_decimal,
            'integerItemType': self._validate_integer,
            'dateTimeItemType': self._validate_datetime,
            'booleanItemType': self._validate_boolean
        }

    def load_taxonomy(self, schema_file: Path) -> None:
        """Load and parse a taxonomy schema file."""
        try:
            # Parse the schema
            schema_doc = etree.parse(str(schema_file))

            # Extract namespace information
            target_ns = schema_doc.getroot().get('targetNamespace')
            if not target_ns:
                raise ValueError(f"Schema {schema_file} has no target namespace")

            # Parse and cache concept definitions
            self._extract_concept_definitions(schema_doc, target_ns)

            # Create XML Schema object for validation
            self.taxonomies[target_ns] = etree.XMLSchema(schema_doc)

        except Exception as e:
            raise ValueError(f"Error loading taxonomy {schema_file}: {str(e)}")

    def _extract_concept_definitions(self, schema_doc: etree.ElementTree, namespace: str) -> None:
        """Extract and cache concept definitions from schema."""
        root = schema_doc.getroot()
        ns = {'xs': 'http://www.w3.org/2001/XMLSchema',
              'xbrli': 'http://www.xbrl.org/2003/instance'}

        for element in root.findall('.//xs:element', ns):
            name = element.get('name')
            if name:
                concept_key = f"{namespace}:{name}"

                # Get type information
                type_name = element.get('type', '').split(':')[-1]
                substitution_group = element.get('substitutionGroup', '').split(':')[-1]

                # Get period type from annotation/documentation if available
                period_type = self._extract_period_type(element, ns)

                # Get balance attribute (debit/credit) if available
                balance = element.get('{http://www.xbrl.org/2003/instance}balance')

                self.concept_info[concept_key] = {
                    'name': name,
                    'type': type_name,
                    'substitutionGroup': substitution_group,
                    'periodType': period_type,
                    'balance': balance,
                    'namespace': namespace
                }

    def _extract_period_type(self, element: etree.Element, ns: Dict[str, str]) -> Optional[str]:
        """Extract period type from element annotation."""
        annotation = element.find('.//xs:annotation/xs:documentation', ns)
        if annotation is not None and 'periodType' in annotation.text:
            return 'duration' if 'duration' in annotation.text.lower() else 'instant'
        return None

    def validate_concept(self, concept_name: str, value: any, context: Dict) -> ValidationResult:
        """Validate a single concept against its taxonomy definition."""
        errors = []
        warnings = []

        # Check if concept exists in taxonomy
        if concept_name not in self.concept_info:
            return ValidationResult(False, [f"Concept {concept_name} not found in taxonomy"], [])

        concept = self.concept_info[concept_name]

        # Validate data type
        type_name = concept['type']
        if type_name in self.allowed_types:
            type_validator = self.allowed_types[type_name]
            type_result = type_validator(value)
            if not type_result.is_valid:
                errors.extend(type_result.errors)
        else:
            warnings.append(f"Unknown type {type_name} for concept {concept_name}")

        # Validate period type
        if concept['periodType']:
            period_result = self._validate_period_type(concept['periodType'], context)
            if not period_result.is_valid:
                errors.extend(period_result.errors)

        # Validate balance type if applicable
        if concept['balance']:
            balance_result = self._validate_balance(concept['balance'], value)
            if not balance_result.is_valid:
                errors.extend(balance_result.errors)

        return ValidationResult(len(errors) == 0, errors, warnings)

    def _validate_monetary(self, value: any) -> ValidationResult:
        """Validate monetary type values."""
        try:
            if not isinstance(value, (int, float, Decimal)):
                return ValidationResult(False, ["Monetary value must be numeric"], [])
            return ValidationResult(True, [], [])
        except:
            return ValidationResult(False, ["Invalid monetary value"], [])

    def _validate_string(self, value: any) -> ValidationResult:
        """Validate string type values."""
        if not isinstance(value, str):
            return ValidationResult(False, ["Value must be a string"], [])
        return ValidationResult(True, [], [])

    def _validate_decimal(self, value: any) -> ValidationResult:
        """Validate decimal type values."""
        try:
            Decimal(str(value))
            return ValidationResult(True, [], [])
        except:
            return ValidationResult(False, ["Value must be a valid decimal"], [])

    def _validate_integer(self, value: any) -> ValidationResult:
        """Validate integer type values."""
        try:
            int(value)
            return ValidationResult(True, [], [])
        except:
            return ValidationResult(False, ["Value must be a valid integer"], [])

    def _validate_datetime(self, value: any) -> ValidationResult:
        """Validate datetime type values."""
        try:
            if isinstance(value, datetime):
                return ValidationResult(True, [], [])
            if isinstance(value, str):
                datetime.fromisoformat(value.replace('Z', '+00:00'))
                return ValidationResult(True, [], [])
            return ValidationResult(False, ["Invalid datetime format"], [])
        except:
            return ValidationResult(False, ["Value must be a valid datetime"], [])

    def _validate_boolean(self, value: any) -> ValidationResult:
        """Validate boolean type values."""
        if isinstance(value, bool):
            return ValidationResult(True, [], [])
        if isinstance(value, str):
            if value.lower() in ('true', 'false', '1', '0'):
                return ValidationResult(True, [], [])
        return ValidationResult(False, ["Value must be a valid boolean"], [])

    def _validate_period_type(self, required_type: str, context: Dict) -> ValidationResult:
        """Validate period type matches context."""
        if required_type == 'instant':
            if 'instant' not in context:
                return ValidationResult(False, ["Context must have instant date for instant period type"], [])
        elif required_type == 'duration':
            if 'startDate' not in context or 'endDate' not in context:
                return ValidationResult(False, ["Context must have start and end dates for duration period type"], [])
        return ValidationResult(True, [], [])

    def _validate_balance(self, balance_type: str, value: any) -> ValidationResult:
        """Validate balance type (debit/credit)."""
        try:
            numeric_value = Decimal(str(value))
            if balance_type == 'credit' and numeric_value < 0:
                return ValidationResult(False, ["Credit balance should be positive"], [])
            if balance_type == 'debit' and numeric_value > 0:
                return ValidationResult(False, ["Debit balance should be negative"], [])
            return ValidationResult(True, [], [])
        except:
            return ValidationResult(False, ["Invalid numeric value for balance validation"], [])

    def validate_context(self, context: Dict) -> ValidationResult:
        """Validate context structure and content."""
        errors = []
        warnings = []

        # Check required context elements
        if 'entity' not in context:
            errors.append("Context must have an entity identifier")

        # Validate period
        if 'instant' in context:
            if 'startDate' in context or 'endDate' in context:
                errors.append("Context cannot have both instant and duration dates")
        elif 'startDate' in context and 'endDate' in context:
            if context['startDate'] > context['endDate']:
                errors.append("Context period start date must be before end date")
        else:
            errors.append("Context must have either instant date or start/end dates")

        # Validate entity identifier
        if 'entity' in context:
            if not context['entity']:
                errors.append("Entity identifier cannot be empty")
            if ':' not in context['entity']:
                warnings.append("Entity identifier should include scheme prefix")

        return ValidationResult(len(errors) == 0, errors, warnings)

    def validate_unit(self, unit: Dict) -> ValidationResult:
        """Validate unit structure and measures."""
        errors = []
        warnings = []

        if not unit.get('measures'):
            errors.append("Unit must have at least one measure")
            return ValidationResult(False, errors, warnings)

        # Validate measures format
        for measure in unit['measures']:
            if ':' not in measure:
                warnings.append(f"Measure {measure} should include namespace prefix")

            # Check for standard units
            if measure.startswith('iso4217:'):
                if measure[8:] not in self._get_valid_currencies():
                    warnings.append(f"Unknown currency code: {measure[8:]}")
            elif measure == 'xbrli:pure':
                continue  # Valid pure unit
            elif measure == 'xbrli:shares':
                continue  # Valid shares unit
            else:
                warnings.append(f"Non-standard unit measure: {measure}")

        # Check divide relationship if present
        if unit.get('divide', False):
            if not (unit.get('numerator') and unit.get('denominator')):
                errors.append("Divide units must have both numerator and denominator")

        return ValidationResult(len(errors) == 0, errors, warnings)

    def _get_valid_currencies(self) -> Set[str]:
        """Return set of valid ISO 4217 currency codes."""
        return {
            'USD', 'EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'CAD', 'CNY', 'HKD', 'NZD',
            'SEK', 'KRW', 'SGD', 'NOK', 'MXN', 'INR', 'RUB', 'ZAR', 'TRY', 'BRL',
            # Add more as needed
        }