# cli.py
import argparse
from pathlib import Path
from processor import XBRLProcessor, XBRLFolderProcessor


def main():
    parser = argparse.ArgumentParser(description='XBRL Document Processor')
    parser.add_argument('input', type=str, help='Path to XBRL file or folder')
    parser.add_argument('--validate', action='store_true', help='Validate the XBRL document')
    parser.add_argument('--export-json', type=str, help='Export to JSON file')
    parser.add_argument('--export-csv', type=str, help='Export to CSV file')

    args = parser.parse_args()

    try:
        input_path = Path(args.input)

        if not input_path.exists():
            print(f"Error: Path {input_path} does not exist")
            return 1

        # Automatically detect if it's a file or folder
        if input_path.is_dir():
            processor = XBRLFolderProcessor()
            print(f"Processing XBRL files in {input_path}...")
            processor.process_folder(input_path)
        else:
            processor = XBRLProcessor()
            print(f"Processing {input_path}...")
            processor.load_instance(input_path)

            # Check for related files
            base_path = input_path.parent
            taxonomy_path = base_path / f"{input_path.stem}.xsd"
            calculation_path = base_path / f"{input_path.stem}-calculation.xml"

            if taxonomy_path.exists():
                print(f"Loading taxonomy: {taxonomy_path}")
                processor.load_taxonomy(taxonomy_path)

            if calculation_path.exists():
                print(f"Loading calculation linkbase: {calculation_path}")
                processor.load_calculation(calculation_path)

        # Handle validation and exports
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