"""Read a synthetic benchmark XLSX without loading millions of cells in memory."""
import json
import sys
import zipfile
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
path, count = sys.argv[1], int(sys.argv[2])
with zipfile.ZipFile(path) as archive:
    assert archive.testzip() is None
    strings = ["".join(node.itertext()) for node in ET.fromstring(archive.read("xl/sharedStrings.xml"))]

    def cells(row):
        values = {}
        for cell in row:
            value = cell.find(f"{NS}v")
            if value is None:
                values[cell.attrib["r"].rstrip("0123456789")] = None
            else:
                values[cell.attrib["r"].rstrip("0123456789")] = strings[int(value.text)] if cell.get("t") == "s" else value.text
        return values

    checked = {}
    for sheet, start in [(3, 6), (4, 21)]:
        seen = 0
        header = {}
        with archive.open(f"xl/worksheets/sheet{sheet}.xml") as source:
            for event, row in ET.iterparse(source, events=("end",)):
                if row.tag != f"{NS}row":
                    continue
                number = int(row.get("r"))
                values = cells(row)
                if number == 20 and sheet == 4:
                    header = {value: key for key, value in values.items()}
                if number >= start:
                    index = number - start
                    assert values["A" if sheet == 3 else header["상품코드"]] == f"SYNTHETIC-{index}"
                    if sheet == 3:
                        assert values["D"] == "0" and values["G"] == "완료 13주 수요이력 부족"
                    else:
                        assert values[header["현지 가용재고(EA)"]] == str(index)
                        assert values[header["12월 연결 계절지수"]] == "1"
                        assert values[header["V3 원시 필요량(EA)"]] is None
                    seen += 1
                row.clear()
        assert seen == count, (sheet, seen, count)
        checked[f"sheet{sheet}"] = seen
    print(json.dumps({"zip_crc_valid": True, "verified_rows": checked, "all_skus_and_sample_fields_equal": True}))
