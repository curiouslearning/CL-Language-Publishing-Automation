def read_unity_url_from_sheet(sheets_service,sheet_id):
    try:
        sheet = sheets_service.spreadsheets().get(
            spreadsheetId=sheet_id,
            ranges=["metadata!D1"],
            fields="sheets(data(rowData(values(userEnteredValue,hyperlink))))"
        ).execute()

        cell = sheet['sheets'][0]['data'][0]['rowData'][0]['values'][0]
        text = cell.get('userEnteredValue', {}).get('stringValue', '')
        url = cell.get('hyperlink', None)
        print(f"🔍 Cell Text: {text}")
        if url:
            print(f"✅ UNITY URL: {url}")
            return url
        else:
            print("❌ No hyperlink found in metadata!D1")
            return False
    except (KeyError, IndexError):
        print("❌ Failed to read cell metadata!D1")
        return False

if __name__ == "__main__":
    print("❌ Please run this via fetch_lang_sheet.py to pass sheets_service and sheet_id")