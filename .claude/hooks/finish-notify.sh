#!/bin/bash
# Market Oracle AI — Windows toast notification when Claude finishes a session
# Uses PowerShell balloon tooltip (works on all Windows 10/11 without extra packages)

powershell.exe -NoProfile -NonInteractive -Command "
  Add-Type -AssemblyName System.Windows.Forms
  \$n = New-Object System.Windows.Forms.NotifyIcon
  \$n.Icon = [System.Drawing.SystemIcons]::Information
  \$n.Visible = \$true
  \$n.ShowBalloonTip(6000, 'Claude Code', 'Task finished — Market Oracle AI', [System.Windows.Forms.ToolTipIcon]::None)
  Start-Sleep -Milliseconds 6500
  \$n.Dispose()
" 2>/dev/null || true

exit 0
