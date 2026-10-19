@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 goto failed_no_directory

echo === Upload remote-b-hub to GitHub ===
echo This commits all non-ignored project changes and pushes the current branch.
echo Credentials and CAD output must stay excluded by .gitignore.
echo.
where git >nul 2>&1
if errorlevel 1 goto missing_git
git rev-parse --show-toplevel
if errorlevel 1 goto failed
git symbolic-ref --quiet --short HEAD
if errorlevel 1 goto detached
git remote get-url origin
if errorlevel 1 goto failed
git var GIT_AUTHOR_IDENT
if errorlevel 1 goto failed

echo.
echo [1/4] Checking Python syntax and COM regression tests...
py -3 -m py_compile windows-b\solidworks_box.py windows-b\sw_constraints.py windows-b\probe_selection_manager.py
if errorlevel 1 goto failed
py -3 -m unittest discover -s tests -p test_sw_constraints.py -v
if errorlevel 1 goto failed
git diff --check
if errorlevel 1 goto failed

echo.
echo [2/4] Staging project changes...
git add --all
if errorlevel 1 goto failed
git diff --cached --check
if errorlevel 1 goto failed
git diff --cached --quiet
if errorlevel 2 goto failed
if errorlevel 1 goto commit_changes
echo No new changes to commit. Existing local commits will still be pushed.
goto push_changes

:commit_changes
echo.
echo [3/4] Creating commit...
git diff --cached --stat
git commit -m "Update project files"
if errorlevel 1 goto failed

:push_changes
echo.
echo [4/4] Pushing to origin...
git push --set-upstream origin HEAD
if errorlevel 1 goto push_failed
echo.
echo SUCCESS: GitHub is up to date for the branch shown above.
echo Other devices: git pull --ff-only
echo Restart the Windows B agent after updating its Python modules.
popd
if /I not "%~1"=="--no-pause" pause
exit /b 0

:missing_git
echo ERROR: Install Git for Windows, then run this script again.
goto failed

:detached
echo ERROR: Detached HEAD. Switch to your intended branch first.
goto failed

:push_failed
echo ERROR: Push failed. Your local commit is preserved.
echo Check the GitHub login, network, and remote branch history above.
echo If GitHub has newer commits, reconcile them before trying again.
echo This script never force-pushes or resets your files.
goto failed

:failed
echo.
echo FAILED: Upload was not completed. Read the error above.
popd
:failed_no_directory
if /I not "%~1"=="--no-pause" pause
exit /b 1
