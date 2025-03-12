@echo off

cd ext\kit-cgns
call repo.bat build
cd ..\..
robocopy .\ext\kit-cgns\_build\windows-x86_64\release\exts .\source\extensions /COPYALL /E
call repo.bat build
robocopy .\ext\kit-cgns\_build\windows-x86_64\release\exts .\_build\windows-x86_64\release\exts /COPYALL /E