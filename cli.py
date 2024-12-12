# cli.py
import argparse
from pathlib import Path
from processor import XBRLProcessor


def main():
    parser = argparse.ArgumentParser(description='XBRL Document Processor')
    parser.add_argument('input_file', type=str, help='Path to input XBRL file')
    parser.add_argument('--validate', action='store_true', help='Validate the XBRL document')
    parser.add_argument('--export-json', type=str, help='Export to JSON file')
    parser.add_argument('--export-csv', type=str, help='Export to CSV file')

    args = parser.parse_args()

    try:
        processor = XBRLProcessor()
        input_path = Path(args.input_file)
        base_path = input_path.parent

        print(f"Processing {input_path}...")

        # Load all necessary files
        processor.load_instance(input_path)

        # Try to load corresponding taxonomy and calculation files
        taxonomy_path = base_path / f"{input_path.stem}.xsd"
        calculation_path = base_path / f"{input_path.stem}-calculation.xml"

        if taxonomy_path.exists():
            print(f"Loading taxonomy: {taxonomy_path}")
            processor.load_taxonomy(taxonomy_path)

        if calculation_path.exists():
            print(f"Loading calculation linkbase: {calculation_path}")
            processor.load_calculation(calculation_path)

        if args.validate:
            errors = processor.validate()
            if errors:
                print("\nValidation errors found:")
                for error in errors:
                    print(f"- {error}")
            else:
                print("\nValidation successful!")

        if args.export_json:
            json_path = Path(args.export_json)
            processor.export_to_json(json_path)
            print(f"\nExported to JSON: {json_path}")

        if args.export_csv:
            csv_path = Path(args.export_csv)
            processor.export_to_csv(csv_path)
            print(f"\nExported to CSV: {csv_path}")

    except Exception as e:
        print(f"Error: {str(e)}")
        return 1

    return 0


if __name__ == '__main__':
    exit(main())