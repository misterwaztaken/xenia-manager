# Xenia Manager

> [!IMPORTANT]
> This is unfinished! Xenia Manager is a Work-In-Progress.

### What is Xenia Manager?
Xenia Manager is a Python-based GUI manager for installing different versions of Xenia and managing Xbox 360 games and dashboards

### Features
- Install Xenia directly inside the app
    - Install Xenia Canary [xenia-canary/xenia-canary-releases](https://github.com/xenia-canary/xenia-canary-releases)
    - Install Xenia Canary (from older release repo) [xenia-canary/xenia-canary](https://github.com/xenia-canary/xenia-canary)
    - Install Xenia Canary (Dashboard Experiment aka db-experiment) [seven7000real/xenia-canary](https://github.com/seven7000real/xenia-canary)
    - Install Xenia Canary Netplay [AdrianCassar/xenia-canary](https://github.com/AdrianCassar/xenia-canary)
    - Install Xenia Stable (SUPER OLD, not recommended) [xenia-project/xenia-stable-windows](https://github.com/xenia-project/xenia-stable-windows)
- Install dashboards directly inside the app
    - This includes (most if not all) versions from November 30, 2006 to April 5, 2014. 
    - 2.0.4548.0 [Blades] - 2.0.16747 [Metro]
    - Dashboards are downloaded from [this repository](https://github.com/misterwaztaken/xbox360-dashboard-collection)
- Launch dashboards directly inside the app
    - Xenia is the main muscle here, but most (except Metro, functionality has not been implemented yet) only work on [db-experiment](https://github.com/seven7000real/xenia-canary) because it's the only one that focuses on dashboard functionability. You can download it on its own or in Xenia Manager.
    - Furthermore, normal Canary loads the dashboards incorrectly. Boot animations are fine though on all versions.
- Auto-detect games
    - Functionality is a bit wonky, but it will definetly jot down if you have games in the games folder and under the root of the main.py. eIf you're disorganized, of course. Like me :)
- Auto-detect emulators
    - Again, functionability is a bit wonky, but if you have emulators in the root directory, it will jot down those emulators. However, it will be unable to find version information for said emulators, and specific names (if any.)
    - For example, if it found two un-named xenia-canary.exe's, it wouldn't label one db-experiment and the other the normal Xenia Canary. 
    - But it can seperate Xenia Stable **(reminder: it can infer, not detect)** from Xenia Canary and Xenia Canary Netplay based off of the file name. So you can be somewhat organized! Unlike me :)
- Keep track of downloaded emulators
    - Neat feature is that all downloaded emulators (keep in mind you can have as many from one version as you want) are kept track of. So in "Configure Manager > Emulators" you can see what emulators you have installed.
- Uninstall installed emulators
    - I'm going to start sounding like an advertisement, but you can also keep your uninstalls hassle-free with... the uninstall button. Wow.
- Specify other directories
    - If you have games in other directories, such as a drive, you can add/remove those directories. For example, you have games on a USB drive. Boom. Games show up in the Games tab. Wow.


### Planned features/bugfixes (should make these all issues lmao)
- APPLICATION RELEASES WITH PYINSTALLER (i'm trying to get this working for portability, so bear with me!)
- Fix issue with requests where app freezes if the internet sucks or is school wifi (you know where this is going)
- Fix issue where downloaded dashboards download to another folder under the
main dashboard folder called "dashboards" (quite a handful, I know)
- Add support for Linux, maybe MacOS **<-- BIG MAYBE™**
- Add a cover art view for the Games tab
    - Figure out how to wrangle [IGDB](https://www.igdb.com/) and find title (game) names from the file itself to match a cover image to the ISO
- Enhance repo management (allow for adding of custom Xenia repos, move all repos into a json file)