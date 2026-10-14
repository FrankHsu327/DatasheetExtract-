$env:PYTHONIOENCODING = "utf-8"
$py = ".\.venv-docling\Scripts\python.exe"
$dry = $args[0]
& $py scripts\make_golden_figures.py datasheet\0900766b81703faf.pdf golden\W25Q128JV.golden.json $dry
& $py scripts\make_golden_figures.py datasheet\DS3624LE-00.pdf golden\DS3624LE-00.golden.json $dry
& $py scripts\make_golden_figures.py datasheet\infineon-ez-pd-ccg6-cfp-usb-c-power-delivery-controller-datasheet-en.pdf golden\CCG6.golden.json $dry
& $py scripts\make_golden_figures.py datasheet\MC9S08SC4.pdf golden\MC9S08SC4.golden.json $dry
