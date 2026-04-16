# Market Oracle AI — Task completion sounds
# Called by Stop hook
# Usage: powershell -File .claude/hooks/sound-complete.ps1 [-Result success|warning|error]

param(
    [string]$Result = "success"
)

switch ($Result) {
    "success" {
        # Ascending tones — task completed successfully
        [console]::beep(600, 150)
        [console]::beep(800, 150)
        [console]::beep(1000, 200)
    }
    "warning" {
        # Double mid-tone — completed with warnings
        [console]::beep(400, 300)
        [console]::beep(400, 300)
    }
    "error" {
        # Low tone — something failed
        [console]::beep(200, 500)
    }
    default {
        # Default: same as success
        [console]::beep(600, 150)
        [console]::beep(800, 150)
    }
}
