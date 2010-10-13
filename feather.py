#!/usr/local/bin/python

'''

feather is a tarsnap script that performs and maintains a set of backups
as defined in a yaml configuration file.

TODO:
    - Order of backups (!!omap)
    - use localtime instead of hardcoding UTC

'''


import datetime
import optparse
import os
import re
import signal
import subprocess
import sys
import time
import yaml

class backup_schedule(set):

    def __init__(self, schedule_from_yaml):
        # Reformat schedule into something a little more useable.
        self.schedule = {}
        for item in schedule_from_yaml:
            #{'WEEKLY': [{'period': 604800}, {'always_keep': 6}, 
            #            {'implies': 'MONTHLY'}]}, 
            key = item.keys()[0]
            self.schedule[key] = {}
            for param in item[key]:
                param_key = param.keys()[0]
                if param_key == 'period':
                    self.schedule[key][param_key] = \
                                  datetime.timedelta(seconds=param[param_key])
                else:
                    self.schedule[key][param_key] = param[param_key]

    def __contains__(self, elem):
        return elem in self.schedule

    def __str__(self):
        return str(self.schedule)

    def get_schedule(self, snapshot):
        if 'implies' in self.schedule[snapshot]:
            return [snapshot] + \
                    self.get_schedule(self.schedule[snapshot]['implies'])
        else:
            return [snapshot]

    def schedule_timedelta(self, schedule):
        return self.schedule[schedule]['period']

    def rotate(self, schedule, quantity):
        return quantity > self.schedule[schedule]['always_keep']

    def timeok(self, schedule):
        ts = time.strftime("%H%M", time.gmtime())
        if 'after' in self.schedule[schedule]:
            if self.schedule[schedule]['after'] > ts:
                return False
        if 'before' in self.schedule[schedule]:
            if self.schedule[schedule]['before'] < ts:
                return False
        return True

class ConcurrencyError(Exception):
    def __init__(self, value = "Concurrency Error"):
        self.value = value
    def __str__(self):
        return repr(self.value)

class RecursionError(Exception):
    def __init__(self, value = "Recursion Loop Error"):
        self.value = value
    def __str__(self):
        return repr(self.value)

class MaxRuntime(Exception):
    def __init__(self, value = "Maximum Runtime Exceeded"):
        self.value = value
    def __str__(self):
        return repr(self.value)

class ConfigError(Exception):
    def __init__(self, value = "Configuration Error"):
        self.value = value
    def __str__(self):
        return repr(self.value)

class lock():
    def __init__(self, pidfile):

        if (os.path.isfile(pidfile)):
            f = open(pidfile, "r")
            pid = f.readline()
            f.close()

            try:
                os.kill(int(pid), 0)
                # pid is running..
                raise ConcurrencyError, \
                      "tarsnap already running %s" % pid

            except OSError, err:
                # pid isn't running, so remove the stale pidfile
                os.remove(pidfile)

        # write our pid
        file(pidfile,'w+').write("%s" % str(os.getpid()))


class pr_tarsnap():

    archive_list = []

    def __init__(self, yaml_file, verbosity=None):
        if verbosity: 
            self.verbosity = verbosity
        else:
            self.verbosity = 0

        f = open(yaml_file)
        config = yaml.load(f.read())
        f.close()

        self.max_runtime = config.get('max_runtime', None)
        if self.max_runtime:
            signal.signal(signal.SIGALRM, self.timeout)
            signal.alarm(self.max_runtime)

        self.handle = None
        self.cachedir = config.get('cachedir', None)
        self.keyfile = config.get('keyfile', None)
        self.binpath = config.get('binpath', None)

        self.checkpoint_bytes = config.get('checkpoint_bytes', None)

        self.schedule = backup_schedule(config['schedule'])

        # Reformat schedule into something a little more useable.
        self.backups = {}
        for item in config['backups']:
            #{'_usr_home_drue_irclogs': 
            # [{'schedule': 'realtime'}, {'path': '/usr/home/drue/irclogs'}]}
            key = item.keys()[0]
            self.backups[key] = {}
            for param in item[key]:
                param_key = param.keys()[0]
                self.backups[key][param_key] = param[param_key]
            if 'schedule' not in self.backups[key]:
                raise ConfigError, "'schedule' not defined for backup %s" % key
            if 'path' not in self.backups[key]:
                raise ConfigError, "'path' not defined for backup %s" % key

        self.populate_archive_list()

    def timeout(self, signum, frame):
        if self.handle:
            self.handle.kill()
        raise MaxRuntime, "Timeout of %ss exceeded; aborting" % self.max_runtime

    def tarsnap_cmd(self):
        cmd = []
        if self.binpath:
            cmd.append("%s/tarsnap" % self.binpath)
        else:
            cmd.append("tarsnap")
        if self.cachedir:
            cmd += ["--cachedir", self.cachedir]
        if self.keyfile:
            cmd += ["--keyfile", self.keyfile]
        if self.verbosity > 0:
            cmd += ["--print-stats"]
            cmd += ["--humanize-numbers"]
        else:
            cmd += ["--no-print-stats"]
        return cmd

    def populate_archive_list(self):
        cmd = self.tarsnap_cmd() + ["--list-archives"]

        if self.verbosity > 1: 
            print "Listing archives using tarsnap --list-archives"
            if self.verbosity > 2: print cmd
        output = self.execute(cmd)
        if self.verbosity > 2: print output
        self.archive_list = output.splitlines()
        self.archive_list.sort()

    def exists(self, base, schedule):
        if self.verbosity > 1: 
            print "Checking if the following exists: %s %s" % (base, schedule)
        pattern = re.compile("^(.*)-(\d+)UTC-(\w+)$")

        # Loop through the list of archives to see if we can find one that
        # is within the schedule for the given path.
        # for instance, if path is /foo/bar and schedule is "DAILY", 
        # look for an archive of /foo/bar made within 24h.
        for archive in self.archive_list: 
            f = pattern.match(archive)
            if not f:
                sys.stderr.write("Archive label format unrecognized: %s\n" % 
                                 archive)
                continue # unrecognized archive

            (archivepath, ts, type) = f.groups()
            if archivepath == base and type == schedule:
                try: 
                    ts = datetime.datetime.strptime(ts, "%Y%m%d%H%M")
                except:
                    sys.stderr.write("Unknown timestamp: %s\n" % archive)
                    continue 
                if ((datetime.datetime.utcnow()-ts) < 
                     self.schedule.schedule_timedelta(schedule)):
                    return True

        return False

    def execute(self, cmd):
        self.handle = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
        (stdout, stderr) = self.handle.communicate()
        if self.handle.returncode > 0:
            print stderr
        return stdout

    def run_backups(self):
        for backup in self.backups:
            backup_path = self.backups[backup]['path']
            backup_schedule = self.backups[backup]['schedule']
            try:
                snapshots = self.schedule.get_schedule(backup_schedule)
            except RuntimeError:
                raise RecursionError, "Loop detected in backup configuration"

            for snapshot in snapshots:
                if self.verbosity > 1: 
                    print "Processing", backup, snapshot
                if self.exists(backup, snapshot):
                    # backup already existing within schedule window
                    continue
                if not self.schedule.timeok(snapshot):
                    # Skip the snapshot if current time is not within
                    # before: and after:, if set.
                    if self.verbosity > 1:
                        print "Skipping due to time of day:", backup, snapshot
                    continue
                ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%MUTC")
                archive_name = backup+"-"+ts+"-"+snapshot
                if self.verbosity > 0: 
                    print "Taking backup", archive_name
                cmd = self.tarsnap_cmd() + [
                       "--checkpoint-bytes", str(self.checkpoint_bytes),
                       "--one-file-system", 
                       "-c", "-f", archive_name, backup_path]
                if self.verbosity > 2: 
                    print cmd
                output = self.execute(cmd)
                if self.verbosity > 2: 
                    print output


    def prune_backups(self):
        ''' 
            prune_backups checks two conditions before removing an archive.
            1) That the theoretical amount of backups exist.  For instance, 
               if we keep weekly backups for 6 weeks, do not delete any weekly
               backups if we only have 5 of them (even if they are older).  
               This ensures that if backups are broken, old archives will never
               automatically be removed.
            2) That the archive to remove is older than the predefined period
               of time.

        '''
        self.populate_archive_list()
        self.archive_list.sort()
        pattern = re.compile("^(.*)-(\d+)UTC-(\w+)$")

        quantity = {}
        # Count up how many of each type of archive exist
        for archive in self.archive_list: 
            f = pattern.match(archive)
            if not f:
                sys.stderr.write("Unrecognizable archive: %s\n" % archive)
                continue # unrecognized archive

            (path, ts, type) = f.groups()
            if type in quantity:
                quantity[type] += 1
            else:
                quantity[type] = 1

        for archive in self.archive_list:
            f = pattern.match(archive)
            if not f:
                sys.stderr.write("Unrecognizable archive: %s\n" % archive)
                continue # unrecognized archive

            (path, ts, type) = f.groups()

            try: 
                ts = datetime.datetime.strptime(ts, "%Y%m%d%H%M")
            except:
                sys.stderr.write("Unknown timestamp: %s\n" % archive)
                continue 

            if ((datetime.datetime.utcnow()-ts) > 
                         self.schedule.schedule_timedelta(type)):
                if self.schedule.rotate(type, quantity[type]):
                    if self.verbosity > 0: print "Deleting archive", archive
                    quantity[type] -= 1 # remove an item from quantity dict
                    cmd = self.tarsnap_cmd() + ["-d", "-f", archive]
                    if self.verbosity > 2: print cmd
                    output = self.execute(cmd)
                    if self.verbosity > 2: print output


def main():

    usage = "usage: %prog [options] config_file"
    parser = optparse.OptionParser(usage)
    parser.add_option("-v", action="count", dest="verbosity", 
                      help="Verbosity; Additional -v options will provide "
                           "additional detail.")

    (options, args) = parser.parse_args()
    if len(args) != 1:
        parser.error("YAML config file not specified")

    PIDFILE = "/tmp/feather.pid"
    lock(PIDFILE)
    os.nice(20)
    b = pr_tarsnap(args[0], options.verbosity)
    b.run_backups()
    b.prune_backups()

if __name__ == '__main__':
    main()
