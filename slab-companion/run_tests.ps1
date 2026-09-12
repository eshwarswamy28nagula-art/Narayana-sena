$ErrorActionPreference = 'Stop'
$baseUrl = 'http://127.0.0.1:5050'
$tests = @(
  @{ command = 'Find the scholarship documents required for students.'; changed = $false },
  @{ command = 'Find the hostel application process.'; changed = $false },
  @{ command = 'Find the B.Tech CSE fee structure.'; changed = $false },
  @{ command = 'Find the exam timetable.'; changed = $false },
  @{ command = 'Find the admission process.'; changed = $false },
  @{ command = 'Open the contact page.'; changed = $false },
  @{ command = 'Give me a short explanation of the admission process.'; changed = $false },
  @{ command = 'Find today''s weather.'; changed = $false },
  @{ command = 'Find scholarship information in adaptation mode.'; changed = $true },
  @{ command = 'Find hostel information in adaptation mode.'; changed = $true }
)

$health = Invoke-RestMethod -Uri "$baseUrl/health" -TimeoutSec 5
if (-not $health.ok) { throw 'Waypoint health check failed.' }

foreach ($test in $tests) {
  $body = $test | ConvertTo-Json
  $result = Invoke-RestMethod -Uri "$baseUrl/api/run" -Method Post -ContentType 'application/json' -Body $body
  [pscustomobject]@{
    Command = $test.command
    Section = $result.goal.section
    Adapted = $result.task.adapted
    Recoveries = $result.task.recovery_attempts
    Answer = $result.task.answer
  }
}
