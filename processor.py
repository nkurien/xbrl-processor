# xbrl_processor.py
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from pathlib import Path
import json
import csv
from datetime import datetime
from lxml import etree
import pandas as pd

@dataclass
class XBRLContext:
    id: str
    entity: str
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    instant: Optional[datetime] = None
    scenario: Optional[Dict[str, Any]] = None

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
            'xbrli': 'http://www.xbrl.org/2003/instance',
            'ix': 'http://www.xbrl.org/2013/inlineXBRL',
            'link': 'http://www.xbrl.org/2003/linkbase',
            'xlink': 'http://www.w3.org/1999/xlink'
        }
        self.contexts: Dict[str, XBRLContext] = {}
        self.facts: List[XBRLFact] = []
        self.units: Dict[str, str] = {}
        
    def parse_file(self, file_path: Path) -> None:
        """Parse an XBRL instance document."""
        try:
            tree = etree.parse(str(file_path))
            root = tree.getroot()
            
            # Parse contexts first as they're referenced by facts
            self._parse_contexts(root)
            # Parse units
            self._parse_units(root)
            # Parse facts
            self._parse_facts(root)
            
        except etree.XMLSyntaxError as e:
            raise ValueError(f"Invalid XML syntax: {str(e)}")
        except Exception as e:
            raise ValueError(f"Error parsing XBRL file: {str(e)}")
    
    def _parse_contexts(self, root: etree.Element) -> None:
        """Extract all contexts from the XBRL document."""
        for context in root.findall('.//xbrli:context', self.namespaces):
            context_id = context.get('id')
            if not context_id:
                continue
                
            entity = self._extract_entity(context)
            period_data = self._extract_period(context)
            scenario = self._extract_scenario(context)
            
            self.contexts[context_id] = XBRLContext(
                id=context_id,
                entity=entity,
                **period_data,
                scenario=scenario
            )
    
    def _extract_entity(self, context: etree.Element) -> str:
        """Extract entity identifier from context."""
        entity_elem = context.find('.//xbrli:entity/xbrli:identifier', self.namespaces)
        return entity_elem.text if entity_elem is not None else ''
    
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
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse XBRL date string to datetime object."""
        return datetime.strptime(date_str, '%Y-%m-%d')
    
    def _extract_scenario(self, context: etree.Element) -> Optional[Dict[str, Any]]:
        """Extract scenario information from context."""
        scenario = context.find('.//xbrli:scenario', self.namespaces)
        if scenario is None:
            return None
            
        return {'dimensions': self._extract_dimensions(scenario)}
    
    def _extract_dimensions(self, scenario: etree.Element) -> Dict[str, str]:
        """Extract dimensional information from scenario."""
        dimensions = {}
        for dim in scenario.getchildren():
            if dim.tag.endswith('explicitMember'):
                dimension = dim.get('dimension')
                value = dim.text
                if dimension and value:
                    dimensions[dimension] = value
        return dimensions
    
    def _parse_units(self, root: etree.Element) -> None:
        """Extract unit definitions."""
        for unit in root.findall('.//xbrli:unit', self.namespaces):
            unit_id = unit.get('id')
            measure = unit.find('.//xbrli:measure', self.namespaces)
            if unit_id and measure is not None:
                self.units[unit_id] = measure.text
    
    def _parse_facts(self, root: etree.Element) -> None:
        """Extract all facts from the XBRL document."""
        # Handle both standard XBRL and inline XBRL
        for elem in root.xpath('.//*[not(self::xbrli:*) and not(self::link:*)]', 
                             namespaces=self.namespaces):
            context_ref = elem.get('contextRef')
            if context_ref is None or context_ref not in self.contexts:
                continue
                
            value = self._extract_fact_value(elem)
            if value is not None:
                self.facts.append(XBRLFact(
                    concept=self._get_concept_name(elem),
                    value=value,
                    context_ref=context_ref,
                    unit_ref=elem.get('unitRef'),
                    decimals=self._parse_numeric_attribute(elem.get('decimals')),
                    precision=self._parse_numeric_attribute(elem.get('precision'))
                ))
    
    def _get_concept_name(self, elem: etree.Element) -> str:
        """Get the concept name without namespace prefix."""
        return etree.QName(elem).localname
    
    def _extract_fact_value(self, elem: etree.Element) -> Any:
        """Extract and type-convert fact values."""
        if elem.text is None:
            return None
            
        value = elem.text.strip()
        if not value:
            return None
            
        # Try numeric conversion
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except ValueError:
            return value
    
    def _parse_numeric_attribute(self, value: Optional[str]) -> Optional[int]:
        """Parse numeric attributes like decimals and precision."""
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None
    
    def validate(self) -> List[str]:
        """Perform basic validation of the XBRL document."""
        errors = []
        
        # Check context references
        for fact in self.facts:
            if fact.context_ref not in self.contexts:
                errors.append(f"Fact {fact.concept} references undefined context {fact.context_ref}")
            
            if fact.unit_ref and fact.unit_ref not in self.units:
                errors.append(f"Fact {fact.concept} references undefined unit {fact.unit_ref}")
        
        return errors
    
    def export_to_json(self, output_path: Path) -> None:
        """Export parsed XBRL data to JSON format."""
        data = {
            'contexts': {k: vars(v) for k, v in self.contexts.items()},
            'facts': [vars(f) for f in self.facts],
            'units': self.units
        }
        
        # Convert datetime objects to strings
        json_str = json.dumps(data, default=str, indent=2)
        output_path.write_text(json_str)
    
    def export_to_csv(self, output_path: Path) -> None:
        """Export facts to CSV format."""
        rows = []
        for fact in self.facts:
            context = self.contexts[fact.context_ref]
            row = {
                'concept': fact.concept,
                'value': fact.value,
                'context_id': fact.context_ref,
                'unit': self.units.get(fact.unit_ref, '') if fact.unit_ref else '',
                'entity': context.entity,
                'period_start': context.period_start,
                'period_end': context.period_end,
                'instant': context.instant
            }
            rows.append(row)
        
        df = pd.DataFrame(rows)
        df.to_csv(output_path, index=False)