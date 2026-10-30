Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.GetInstalledVoices() | ForEach-Object { "SAPI: " + $_.VoiceInfo.Name + " | " + $_.VoiceInfo.Gender + " | " + $_.VoiceInfo.Culture }
Write-Output "---onecore---"
try {
  [Windows.Media.SpeechSynthesis.SpeechSynthesizer,Windows.Media,ContentType=WindowsRuntime] | Out-Null
  [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | ForEach-Object { "ONECORE: " + $_.DisplayName + " | " + $_.Language }
} catch { "ERR " + $_.Exception.Message }
