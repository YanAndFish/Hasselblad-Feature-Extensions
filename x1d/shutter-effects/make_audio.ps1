# 本机生成的独立 Ciallo 读音；不使用或改速原游戏录音。
# 默认生成目录限于本模块。Windows SAPI Microsoft Yaoyao 语音。
$ErrorActionPreference = 'Stop'
$moduleRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$destination = Join-Path $moduleRoot 'audio\ciallo-yaoyao.wav'
Add-Type -AssemblyName System.Speech
$speech = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speech.SelectVoice('Microsoft Yaoyao')
    $speech.Rate = 0
    $speech.SetOutputToWaveFile($destination)
    $speech.Speak('恰罗～')
    $speech.SetOutputToNull()
} finally {
    $speech.Dispose()
}
