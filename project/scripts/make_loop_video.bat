@echo off
setlocal enabledelayedexpansion

set "ROOT=%~dp0.."
set "FFMPEG=ffmpeg"
set "OUTDIR=%ROOT%\exports"
set "WORK=%OUTDIR%\work"
set "BG=%ROOT%\assets\images\bg_rain_balcony.png"
set "BGM=%ROOT%\assets\audio\bgm_lofi.wav"
set "RAIN=%ROOT%\assets\audio\rain.wav"
set "ROOM=%ROOT%\assets\audio\room_tone.wav"
set "NOISE=%ROOT%\assets\audio\vinyl_noise.wav"
set "OUT5=%OUTDIR%\lofi_rain_balcony_5m.mp4"
set "OUT30=%OUTDIR%\lofi_rain_balcony_30m.mp4"

if not exist "%OUTDIR%" mkdir "%OUTDIR%"
if not exist "%WORK%" mkdir "%WORK%"

echo [1/3] 5分ループ動画を作成します
echo  - 背景: %BG%
echo  - BGM: %BGM%
echo  - 雨音: %RAIN%
echo  - 環境音: %ROOM%
echo  - ノイズ: %NOISE%

%FFMPEG% -loop 1 -i "%BG%" ^
  -i "%BGM%" ^
  -i "%RAIN%" ^
  -i "%ROOM%" ^
  -i "%NOISE%" ^
  -filter_complex ^
    "[0:v]scale=1920:1080,zoompan=z='min(zoom+0.0008,1.10)':d=900:s=1920x1080:fps=30,format=yuv420p[v]; ^
     [1:a]volume=0.95[a1]; ^
     [2:a]volume=0.22[a2]; ^
     [3:a]volume=0.12[a3]; ^
     [4:a]volume=0.05[a4]; ^
     [a1][a2][a3][a4]amix=inputs=4:duration=longest:normalize=0[a]" ^
  -map "[v]" -map "[a]" ^
  -t 00:05:00 -r 30 ^
  -c:v libx264 -pix_fmt yuv420p -profile:v high -preset medium -crf 18 ^
  -c:a aac -b:a 192k ^
  -movflags +faststart ^
  "%OUT5%"

if errorlevel 1 (
  echo 5分版の作成に失敗しました
  exit /b 1
)

echo [2/3] 30分版のconcatリストを作成します
(
  echo file 'lofi_rain_balcony_5m.mp4'
  echo file 'lofi_rain_balcony_5m.mp4'
  echo file 'lofi_rain_balcony_5m.mp4'
  echo file 'lofi_rain_balcony_5m.mp4'
  echo file 'lofi_rain_balcony_5m.mp4'
  echo file 'lofi_rain_balcony_5m.mp4'
) > "%WORK%\concat_30m.txt"

echo [3/3] 30分版を作成します
%FFMPEG% -f concat -safe 0 -i "%WORK%\concat_30m.txt" -c copy "%OUT30%"

if errorlevel 1 (
  echo 30分版の作成に失敗しました
  exit /b 1
)

echo 完了: %OUT5%
echo 完了: %OUT30%
endlocal
