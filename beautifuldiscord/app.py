#!/usr/bin/env python

import os
import sys
import shutil
from distutils.dir_util import copy_tree
from collections import namedtuple
import argparse
import textwrap
import subprocess
import psutil
from beautifuldiscord.asar import Asar


DiscordProcess = namedtuple('DiscordProcess', 'path exe processes')

def discord_process_terminate(self):
    for process in self.processes:
        # terrible
        process.kill()

def discord_process_launch(self):
    with open(os.devnull, 'w') as f:
        subprocess.Popen([os.path.join(self.path, self.exe)], stdout=f, stderr=subprocess.STDOUT)

def discord_process_resources_path(self):
    if sys.platform == 'darwin':
        # OS X has a different resources path
        # Application directory is under <[EXE].app/Contents/MacOS/[EXE]>
        # where [EXE] is Discord Canary, Discord PTB, etc
        # Resources directory is under </Applications/[EXE].app/Contents/Resources/app.asar>
        # So we need to fetch the folder based on the executable path.
        # Go two directories up and then go to Resources directory.
        return os.path.abspath(os.path.join(self.path, '..', 'Resources'))
    return os.path.join(self.path, 'resources')

DiscordProcess.terminate = discord_process_terminate
DiscordProcess.launch = discord_process_launch
DiscordProcess.resources_path = property(discord_process_resources_path)

def parse_args():
    description = """\
Unpacks Discord and adds CSS/JS hot-reloading.

Discord has to be open for this to work. When this tool is ran,
Discord will close and then be relaunched when the tool completes.
"""
    parser = argparse.ArgumentParser(description=description.strip())
    parser.add_argument('--legacy', action='store_true', help='This script is now deprecated, please see https://github.com/UraYukimitsu/DiscordBootstrap - if you wish to use it anyway, passing this switch is necessary.')
    parser.add_argument('--css', metavar='file', help='Location of the CSS file to watch')
    parser.add_argument('--js', metavar='file', help='Location of the JS file to watch')
    parser.add_argument('--node', metavar='dir', help='Directory containing Node modules callable from the JS script')
    parser.add_argument('--nodenew', metavar='dir', help='Directory containing Node modules callable from the JS script - uses the alternate path, use this if the other one doesn\'t work')
    parser.add_argument('--nodenoreload', metavar='dir', help='Adds Node modules without reloading Discord (has the priority over any other switch)')
    parser.add_argument('--nodenoreloadnew', metavar='dir', help='Adds Node modules without reloading Discord (has the priority over any other switch) - uses the alternate path, use this if the other one doesn\'t work')
    parser.add_argument('--revert', action='store_true', help='Reverts any changes made to Discord (does not delete CSS or JS files)')
    args = parser.parse_args()
    return args

def discord_process():
    executables = {}
    for proc in psutil.process_iter():
        try:
            (path, exe) = os.path.split(proc.exe())
        except psutil.AccessDenied:
            pass
        else:
            if exe.startswith('Discord') and not exe.endswith('Helper'):
                entry = executables.get(exe)
                if entry is None:
                    entry = executables[exe] = DiscordProcess(path=path, exe=exe, processes=[])
                entry.processes.append(proc)
    if len(executables) == 0:
        raise RuntimeError('Could not find Discord executable.')
    if len(executables) == 1:
        r = executables.popitem()
        print('Found {0.exe} under {0.path}'.format(r[1]))
        return r[1]
    lookup = list(executables)
    for index, exe in enumerate(lookup):
        print('%s: Found %s' % (index, exe))
    while True:
        index = input("Discord executable to use (number): ")
        try:
            index = int(index)
        except ValueError as e:
            print('Invalid index passed')
        else:
            if index >= len(lookup) or index < 0:
                print('Index too big (or small)')
            else:
                key = lookup[index]
                return executables[key]

def extract_asar():
    try:
        with Asar.open('./app.asar') as a:
            try:
                a.extract('./app')
            except FileExistsError:
                answer = input('asar already extracted, overwrite? (Y/n): ')

                if answer.lower().startswith('n'):
                    print('Exiting.')
                    return False

                shutil.rmtree('./app')
                a.extract('./app')

        shutil.move('./app.asar', './original_app.asar')
    except FileNotFoundError as e:
        print('WARNING: app.asar not found')
    return True

def main():
    args = parse_args()
    if not args.legacy:
        print('This script is now deprecated, please see https://github.com/UraYukimitsu/DiscordBootstrap\nIf you wish to use it anyway, passing the --legacy switch is necessary.')
        return
    
    try:
        discord = discord_process()
    except Exception as e:
        print(str(e))
        return

    if sys.platform.startswith('linux'):
        user_data_root = os.environ.get('XDG_CONFIG_HOME', os.path.join(os.environ.get('HOME'), '.config'))
    elif sys.platform.startswith('win'):
        user_data_root = os.environ.get('APPDATA')
    elif sys.platform.startswith('darwin'):
        user_data_root = os.path.join(os.environ.get('HOME'), 'Library', 'Application Support')
    else:
        print('Unknown/unsupported OS')
        return False
    user_data_root = os.path.join(user_data_root, os.path.basename(os.path.dirname(discord.path)).lower(), os.path.basename(discord.path).replace('app-', ''))

    if args.css:
        args.css = os.path.abspath(args.css)
    else:
        args.css = os.path.join(discord.resources_path, 'discord-custom.css')
    
    if args.js:
        args.js = os.path.abspath(args.js)
    else:
        args.js = os.path.join(discord.resources_path, 'discord-custom.js')

    if args.nodenoreload:
        copy_tree(os.path.abspath(args.nodenoreload), os.path.join(discord.resources_path, 'app', 'node_modules'))
        return
    if args.nodenoreloadnew:
        copy_tree(os.path.abspath(args.nodenoreloadnew), os.path.join(user_data_root, 'modules', 'discord_desktop_core', 'node_modules'))
        return

    os.chdir(discord.resources_path)

    args.css = os.path.abspath(args.css)

    discord.terminate()

    if args.revert:
        try:
            shutil.rmtree('./app')
            shutil.move('./original_app.asar', './app.asar')
        except FileNotFoundError as e:
            # assume things are fine for now i guess
            print('No changes to revert.')
        else:
            print('Reverted changes, no more CSS and JS hot-reload :(')
    else:
        if extract_asar():
            if not os.path.exists(args.css):
                with open(args.css, 'w', encoding='utf-8') as f:
                    f.write('/* put your custom css here. */\n')

            if not os.path.exists(args.js):
                with open(args.js, 'w', encoding='utf-8') as f:
                    f.write('// put your custom JS here.\n')

            injection_script = textwrap.dedent("""\
                window._fs = require("fs");

                window._cssWatcher = null;
                window._styleTag = null;

                window._jsWatcher = null;
                window._scriptTag = null;

                window.setupCSS = function (path) {
                    var customCSS = window._fs.readFileSync(path, "utf-8");
                    if (window._styleTag === null) {
                        window._styleTag = document.createElement("style");
                        document.head.appendChild(window._styleTag);
                    }
                    window._styleTag.innerHTML = customCSS;
                    if (window._cssWatcher === null) {
                        window._cssWatcher = window._fs.watch(path, {
                                encoding: "utf-8"
                            },
                            function (eventType, filename) {
                                if (eventType === "change") {
                                    var changed = window._fs.readFileSync(path, "utf-8");
                                    window._styleTag.innerHTML = changed;
                                }
                            }
                        );
                    }
                };

                window.tearDownCSS = function () {
                    if (window._styleTag !== null) {
                        window._styleTag.innerHTML = "";
                    }
                    if (window._cssWatcher !== null) {
                        window._cssWatcher.close();
                        window._cssWatcher = null;
                    }
                };

                window.applyAndWatchCSS = function (path) {
                    window.tearDownCSS();
                    window.setupCSS(path);
                };

                window.applyAndWatchCSS('%s');

                window.setupJS = function (path) {
                    var customJS = window._fs.readFileSync(path, "utf-8");
                    if (window._scriptTag === null) {
                        window._scriptTag = document.createElement("script");
                        document.head.appendChild(window._scriptTag);
                    }
                    window._scriptTag.innerHTML = customJS;
                    if (window._jsWatcher === null) {
                        window._jsWatcher = window._fs.watch(path, {
                                encoding: "utf-8"
                            },
                            function (eventType, filename) {
                                if (eventType === "change") {
                                    var changed = window._fs.readFileSync(path, "utf-8");
                                    window._scriptTag.innerHTML = changed;
                                }
                            }
                        );
                    }
                };

                window.tearDownJS = function () {
                    if (window._scriptTag !== null) {
                        window._scriptTag.innerHTML = "";
                    }
                    if (window._jsWatcher !== null) {
                        window._jsWatcher.close();
                        window._jsWatcher = null;
                    }
                };

                window.applyAndWatchJS = function (path) {
                    window.tearDownJS();
                    window.setupJS(path);
                };

                window.applyAndWatchJS('%s');
            """ % (args.css.replace('\\', '\\\\'), args.js.replace('\\', '\\\\')))

            with open('./app/codeInjection.js', 'w', encoding='utf-8') as f:
                f.write(injection_script)

            injection_script_path = os.path.abspath('./app/codeInjection.js').replace('\\', '\\\\')

            reload_script = textwrap.dedent("""\
                mainWindow.webContents.on('dom-ready', function () {
                  mainWindow.webContents.executeJavaScript(
                    require('fs').readFileSync('%s', 'utf-8')
                  );
                });
            """ % injection_script_path)

            use_index = True
            try:
                with open('./app/index.js', 'r', encoding='utf-8') as f:
                    entire_thing = f.read()
            except FileNotFoundError:
                use_index = False
                main_screen_js = os.path.join(user_data_root, 'modules', 'discord_desktop_core', 'app', 'mainScreen.js')
                with open(main_screen_js, 'r', encoding='utf-8') as f:
                    entire_thing = f.read()


            entire_thing = entire_thing.replace("mainWindow.webContents.on('dom-ready', function () {});", reload_script)

            if use_index:
                with open('./app/index.js', 'w', encoding='utf-8') as f:
                    f.write(entire_thing)
            else:
                with open(main_screen_js, 'w', encoding='utf-8') as f:
                    f.write(entire_thing)

            print(
                '\nDone!\n' +
                '\nYou may now edit your %s file,\n' % os.path.abspath(args.css) +
                'as well as your %s file,\n' % os.path.abspath(args.js) +
                "which will be reloaded whenever they're saved.\n" +
                '\nRelaunching Discord now...'
            )
            if args.nodenoreload:
                copy_tree(os.path.abspath(args.node), os.path.join(discord.resources_path, 'app', 'node_modules'))
            if args.node:
                copy_tree(os.path.abspath(args.nodenew), os.path.join(user_data_root, 'modules', 'discord_desktop_core', 'node_modules'))

    discord.launch()


if __name__ == '__main__':
    main()
