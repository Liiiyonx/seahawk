param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,
    [double]$TolerancePt = 5
)

$ErrorActionPreference = "Stop"
$rows = @()

function Inspect-Shape {
    param(
        [object]$Shape,
        [int]$SlideIndex,
        [double]$SlideWidth,
        [double]$SlideHeight
    )

    if ($Shape.Type -eq 6) {
        foreach ($child in $Shape.GroupItems) {
            Inspect-Shape -Shape $child -SlideIndex $SlideIndex -SlideWidth $SlideWidth -SlideHeight $SlideHeight
        }
        return
    }

    $text = ""
    if ($Shape.HasTextFrame -eq -1 -and $Shape.TextFrame.HasText -eq -1) {
        $range = $Shape.TextFrame.TextRange
        $text = $range.Text
        try {
            $boundWidth = [double]$range.BoundWidth
            $boundHeight = [double]$range.BoundHeight
            if (
                ($boundWidth -gt ([double]$Shape.Width + $TolerancePt)) -or
                ($boundHeight -gt ([double]$Shape.Height + $TolerancePt))
            ) {
                $script:rows += [pscustomobject]@{
                    Slide = $SlideIndex
                    Issue = "text-overflow"
                    Shape = $Shape.Name
                    Left = [math]::Round($Shape.Left, 1)
                    Top = [math]::Round($Shape.Top, 1)
                    Width = [math]::Round($Shape.Width, 1)
                    Height = [math]::Round($Shape.Height, 1)
                    TextWidth = [math]::Round($boundWidth, 1)
                    TextHeight = [math]::Round($boundHeight, 1)
                    Text = ($text -replace "`r?`n", " / ")
                }
            }
        }
        catch {}
    }

    if ($Shape.Visible -eq -1) {
        $right = [double]$Shape.Left + [double]$Shape.Width
        $bottom = [double]$Shape.Top + [double]$Shape.Height
        if (
            ([double]$Shape.Left -lt -$TolerancePt) -or
            ([double]$Shape.Top -lt -$TolerancePt) -or
            ($right -gt ($SlideWidth + $TolerancePt)) -or
            ($bottom -gt ($SlideHeight + $TolerancePt))
        ) {
            $script:rows += [pscustomobject]@{
                Slide = $SlideIndex
                Issue = "off-slide"
                Shape = $Shape.Name
                Left = [math]::Round($Shape.Left, 1)
                Top = [math]::Round($Shape.Top, 1)
                Width = [math]::Round($Shape.Width, 1)
                Height = [math]::Round($Shape.Height, 1)
                TextWidth = $null
                TextHeight = $null
                Text = ($text -replace "`r?`n", " / ")
            }
        }
    }
}

$ppt = New-Object -ComObject PowerPoint.Application
$ppt.Visible = -1
$presentation = $null

try {
    $presentation = $ppt.Presentations.Open($InputPath, $true, $false, $true)
    $slideWidth = [double]$presentation.PageSetup.SlideWidth
    $slideHeight = [double]$presentation.PageSetup.SlideHeight

    foreach ($slide in $presentation.Slides) {
        foreach ($shape in $slide.Shapes) {
            Inspect-Shape -Shape $shape -SlideIndex $slide.SlideIndex -SlideWidth $slideWidth -SlideHeight $slideHeight
        }
    }
}
finally {
    if ($null -ne $presentation) {
        try {
            $presentation.Close()
        }
        catch {}
    }
    try {
        $ppt.Quit()
    }
    catch {}
}

$rows | Sort-Object Slide, Issue, Shape | Format-Table -AutoSize -Wrap
