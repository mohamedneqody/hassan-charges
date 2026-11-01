$ErrorActionPreference = "Stop"
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
    $docx = "D:\hassan_charges\مشروع تخرج حسن\عرض_المتحدثين\المتحدث_1_الفكرة.docx"
    $pdf = "D:\hassan_charges\مشروع تخرج حسن\eval_tmp\test_word_export.pdf"
    $doc = $word.Documents.Open($docx)
    $wdExportFormatPDF = 17
    $doc.ExportAsFixedFormat($pdf, $wdExportFormatPDF)
    $doc.Close([ref]$false)
    Write-Output "SUCCESS: Exported to $pdf"
}
catch {
    Write-Error $_
}
finally {
    $word.Quit()
}
