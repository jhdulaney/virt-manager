# Copyright (C) 2013, 2014 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301 USA.

import atexit
import logging
import os
import shlex
import shutil
import sys
import traceback
import unittest
import StringIO

from virtinst import support

from tests import virtinstall, virtclone, virtconvert, virtxml
from tests import utils

os.environ["LANG"] = "en_US.UTF-8"

# Used to ensure consistent SDL xml output
os.environ["HOME"] = "/tmp"
os.environ["DISPLAY"] = ":3.4"

_defaultconn = utils.open_testdefault()

# Location
image_prefix = "/tmp/__virtinst_cli_"
xmldir = "tests/cli-test-xml"
treedir = "%s/faketree" % xmldir
vcdir = "%s/virtconv" % xmldir
compare_xmldir = "%s/compare" % xmldir
virtconv_out = "/tmp/__virtinst_tests__virtconv-outdir"

# Images that will be created by virt-install/virt-clone, and removed before
# each run
new_images = [
    image_prefix + "new1.img",
    image_prefix + "new2.img",
    image_prefix + "new3.img",
    image_prefix + "exist1-clone.img",
    image_prefix + "exist2-clone.img",
]

# Images that are expected to exist before a command is run
exist_images = [
    image_prefix + "exist1.img",
    image_prefix + "exist2.img",
]

exist_files = exist_images
new_files   = new_images
clean_files = (new_images + exist_images)

test_files = {
    'URI-TEST': utils.uri_test,
    'URI-TEST-DEFAULT': utils.uri_test_default,
    'URI-TEST-REMOTE': utils.uri_test_remote,
    'URI-KVM': utils.uri_kvm,
    'URI-KVM-SESSION': utils.uri_kvm_session,
    'URI-KVM-REMOTE': utils.uri_kvm + ",remote",
    'URI-KVM-NODOMCAPS': utils.uri_kvm_nodomcaps,
    'URI-KVM-ARMV7L' : utils.uri_kvm_armv7l,
    'URI-KVM-AARCH64' : utils.uri_kvm_aarch64,
    'URI-KVM-PPC64LE' : utils.uri_kvm_ppc64le,
    'URI-KVM-S390X' : utils.uri_kvm_s390x,
    'URI-KVM-S390X-KVMIBM' : utils.uri_kvm_s390x_KVMIBM,
    'URI-XEN': utils.uri_xen,
    'URI-LXC': utils.uri_lxc,

    'CLONE_DISK_XML'    : "%s/clone-disk.xml" % xmldir,
    'CLONE_STORAGE_XML' : "%s/clone-disk-managed.xml" % xmldir,
    'CLONE_NOEXIST_XML' : "%s/clone-disk-noexist.xml" % xmldir,
    'IMAGE_XML'         : "%s/image.xml" % xmldir,
    'IMAGE_NOGFX_XML'   : "%s/image-nogfx.xml" % xmldir,
    'OVF_IMG1'           : "%s/tests/virtconv-files/ovf_input/test1.ovf" % os.getcwd(),
    'VMX_IMG1'          : "%s/tests/virtconv-files/vmx_input/test1.vmx" % os.getcwd(),

    'NEWIMG1'           : "/dev/default-pool/new1.img",
    'NEWIMG2'           : "/dev/default-pool/new2.img",
    'NEWCLONEIMG1'      : new_images[0],
    'NEWCLONEIMG2'      : new_images[1],
    'NEWCLONEIMG3'      : new_images[2],
    'AUTOMANAGEIMG'     : "/some/new/pool/dir/new",
    'BLOCKVOL'          : '/iscsi-pool/diskvol1',
    'EXISTIMG1'         : "/dev/default-pool/testvol1.img",
    'EXISTIMG2'         : "/dev/default-pool/testvol2.img",
    'EXISTIMG3'         : exist_images[0],
    'EXISTIMG4'         : exist_images[1],
    'EXISTUPPER'        : "/dev/default-pool/UPPER",
    'POOL'              : "default-pool",
    'VOL'               : "testvol1.img",
    'DIR'               : "/var",
    'TREEDIR'           : treedir,
    'MANAGEDNEW1'       : "/dev/default-pool/clonevol",
    'MANAGEDDISKNEW1'   : "/dev/disk-pool/newvol1.img",
    'COLLIDE'           : "/dev/default-pool/collidevol1.img",
    'SHARE'             : "/dev/default-pool/sharevol.img",
}


######################
# Test class helpers #
######################

class Command(object):
    """
    Instance of a single cli command to test
    """
    def __init__(self, cmd):
        self.cmdstr = cmd % test_files
        self.check_success = True
        self.compare_file = None
        self.input_file = None

        self.skip_check = None
        self.compare_check = None

        app, opts = self.cmdstr.split(" ", 1)
        self.app = app
        self.argv = [os.path.abspath(app)] + shlex.split(opts)

    def _launch_command(self, conn):
        logging.debug(self.cmdstr)

        app = self.argv[0]

        oldstdout = sys.stdout
        oldstderr = sys.stderr
        oldstdin = sys.stdin
        oldargv = sys.argv
        try:
            out = StringIO.StringIO()
            sys.stdout = out
            sys.stderr = out
            sys.argv = self.argv
            if self.input_file:
                sys.stdin = file(self.input_file)

            exc = ""
            try:
                if app.count("virt-install"):
                    ret = virtinstall.main(conn=conn)
                elif app.count("virt-clone"):
                    ret = virtclone.main(conn=conn)
                elif app.count("virt-convert"):
                    ret = virtconvert.main(conn=conn)
                elif app.count("virt-xml"):
                    ret = virtxml.main(conn=conn)
            except SystemExit, sys_e:
                ret = sys_e.code
            except Exception:
                ret = -1
                exc = "\n" + "".join(traceback.format_exc())

            if ret != 0:
                ret = -1
            outt = out.getvalue() + exc
            if outt.endswith("\n"):
                outt = outt[:-1]
            return (ret, outt)
        finally:
            sys.stdout = oldstdout
            sys.stderr = oldstderr
            sys.stdin = oldstdin
            sys.argv = oldargv


    def _get_output(self, conn):
        try:
            for i in new_files:
                if os.path.isdir(i):
                    shutil.rmtree(i)
                elif os.path.exists(i):
                    os.unlink(i)

            code, output = self._launch_command(conn)

            logging.debug(output + "\n")
            return code, output
        except Exception, e:
            return (-1, "".join(traceback.format_exc()) + str(e))

    def _skip_msg(self, conn):
        if self.skip_check is None:
            return
        if conn is None:
            raise RuntimeError("skip_check is not None, but conn is None")
        if conn.check_support(self.skip_check):
            return
        return "skipped"

    def run(self, tests):
        err = None

        try:
            conn = None
            for idx in reversed(range(len(self.argv))):
                if self.argv[idx] == "--connect":
                    conn = utils.openconn(self.argv[idx + 1])
                    break

            if not conn:
                raise RuntimeError("couldn't parse URI from command %s" %
                                   self.argv)

            skipmsg = self._skip_msg(conn)
            if skipmsg is not None:
                tests.skipTest(skipmsg)
                return

            code, output = self._get_output(conn)

            if bool(code) == self.check_success:
                raise AssertionError(
                    ("Expected command to %s, but it didn't.\n" %
                     (self.check_success and "pass" or "fail")) +
                     ("Command was: %s\n" % self.cmdstr) +
                     ("Error code : %d\n" % code) +
                     ("Output was:\n%s" % output))

            if self.compare_file:
                if (self.compare_check and not
                    conn.check_support(self.compare_check)):
                    tests.skipTest(
                        "Skipping compare check due to lack of support")
                    return

                # Generate test files that don't exist yet
                filename = self.compare_file
                if utils.REGENERATE_OUTPUT or not os.path.exists(filename):
                    file(filename, "w").write(output)

                if "--print-diff" in self.argv and output.count("\n") > 3:
                    # 1) Strip header
                    # 2) Simplify context lines to reduce churn when
                    #    libvirt or testdriver changes
                    newlines = []
                    for line in output.splitlines()[3:]:
                        if line.startswith("@@"):
                            line = "@@"
                        newlines.append(line)
                    output = "\n".join(newlines)

                utils.diff_compare(output, filename)

        except AssertionError, e:
            err = self.cmdstr + "\n" + str(e)

        if err:
            tests.fail(err)


class _CategoryProxy(object):
    def __init__(self, app, name, default_args, skip_check, compare_check):
        self._app = app
        self._name = name

        self.default_args = default_args
        self.skip_check = skip_check
        self.compare_check = compare_check

    def add_valid(self, *args, **kwargs):
        return self._app.add_valid(self._name, *args, **kwargs)
    def add_invalid(self, *args, **kwargs):
        return self._app.add_invalid(self._name, *args, **kwargs)
    def add_compare(self, *args, **kwargs):
        return self._app.add_compare(self._name, *args, **kwargs)


class App(object):
    def __init__(self, appname):
        self.appname = appname
        self.categories = {}
        self.cmds = []

    def _default_args(self, cli, iscompare, auto_printarg):
        args = ""
        if not iscompare:
            args = "--debug"

        if "--connect " not in cli:
            args += " --connect %(URI-TEST)s"

        if self.appname in ["virt-install"]:
            if "--name " not in cli:
                args += " --name foobar"
            if "--ram " not in cli:
                args += " --ram 64"

        if iscompare and auto_printarg:
            if self.appname == "virt-install":
                if (not cli.count("--print-xml") and
                    not cli.count("--print-step") and
                    not cli.count("--quiet")):
                    args += " --print-step all"

            elif self.appname == "virt-clone":
                if not cli.count("--print-xml"):
                    args += " --print-xml"

        return args


    def add_category(self, catname, default_args,
                     skip_check=None, compare_check=None):
        obj = _CategoryProxy(self, catname, default_args,
                             skip_check, compare_check)
        self.categories[catname] = obj
        return obj

    def _add(self, catname, testargs, valid, compfile,
             skip_check=None, compare_check=None, input_file=None,
             auto_printarg=True):

        category = self.categories[catname]
        args = category.default_args + " " + testargs
        args = (self._default_args(args, bool(compfile), auto_printarg) +
            " " + args)
        cmdstr = "./%s %s" % (self.appname, args)

        cmd = Command(cmdstr)
        cmd.check_success = valid
        if compfile:
            compfile = os.path.basename(self.appname) + "-" + compfile
            cmd.compare_file = "%s/%s.xml" % (compare_xmldir, compfile)
        cmd.skip_check = skip_check or category.skip_check
        cmd.compare_check = compare_check or category.compare_check
        cmd.input_file = input_file
        self.cmds.append(cmd)

    def add_valid(self, cat, args, **kwargs):
        self._add(cat, args, True, None, **kwargs)
    def add_invalid(self, cat, args, **kwargs):
        self._add(cat, args, False, None, **kwargs)
    def add_compare(self, cat, args, compfile, **kwargs):
        self._add(cat, args, not compfile.endswith("-fail"),
                  compfile, **kwargs)



#
# The test matrix
#
# add_valid: A test that should pass
# add_invalid: A test that should fail
# add_compare: Get the generated XML, and compare against the passed filename
#              in tests/clitest-xml/compare/
#

######################
# virt-install tests #
######################

vinst = App("virt-install")

#############################################
# virt-install verbose XML comparison tests #
#############################################

c = vinst.add_category("xml-comparsion", "--connect %(URI-KVM)s --noautoconsole --os-variant fedora20")

# Singleton element test #1, for simpler strings
c.add_compare(""" \
--memory 1024 \
--vcpus 4 --cpuset=1,3-5 \
--cpu host \
--description \"foobar & baz\" \
--boot uefi \
--security type=dynamic \
--security type=none,model=dac \
--numatune 1,2,3,5-7,^6 \
--memorybacking hugepages=on \
--features apic=off \
--clock offset=localtime \
--resource /virtualmachines/production \
--events on_crash=restart \
\
--disk none \
--console none \
--channel none \
--network none \
--controller usb2 \
--graphics spice \
--video vga \
--sound none \
--redirdev none \
--memballoon none \
--smartcard none \
--watchdog default \
--panic default \
--tpm /dev/tpm0 \
--rng /dev/random \
""", "singleton-config-1", compare_check=support.SUPPORT_CONN_VMPORT)

# Singleton element test #2, for complex strings
c.add_compare("""--pxe \
--memory 512,maxmemory=1024 \
--vcpus 4,cores=2,threads=2,sockets=2 \
--cpu foobar,+x2apic,+x2apicagain,-distest,forbid=foo,forbid=bar,disable=distest2,optional=opttest,require=reqtest,match=strict,vendor=meee \
--metadata title=my-title,description=my-description,uuid=00000000-1111-2222-3333-444444444444 \
--boot cdrom,fd,hd,network,menu=off,loader=/foo/bar \
--idmap uid_start=0,uid_target=1000,uid_count=10,gid_start=0,gid_target=1000,gid_count=10 \
--security type=static,label='system_u:object_r:svirt_image_t:s0:c100,c200',relabel=yes \
--numatune 1-3,4,mode=strict \
--memtune hard_limit=10,soft_limit=20,swap_hard_limit=30,min_guarantee=40 \
--blkiotune weight=100,device_path=/home/test/1.img,device_weight=200 \
--memorybacking size=1,unit='G',nodeset='1,2-5',nosharepages=yes,locked=yes \
--features acpi=off,eoi=on,privnet=on,hyperv_spinlocks=on,hyperv_spinlocks_retries=1234,vmport=off,pmu=off \
--clock offset=utc,hpet_present=no,rtc_tickpolicy=merge \
--pm suspend_to_mem=yes,suspend_to_disk=no \
--resource partition=/virtualmachines/production \
--events on_poweroff=destroy,on_reboot=restart,on_crash=preserve,on_lockfailure=ignore \
\
--controller usb3 \
--controller virtio-scsi \
--graphics vnc \
--filesystem /foo/source,/bar/target \
--memballoon virtio \
--watchdog ib700,action=pause \
--tpm passthrough,model=tpm-tis,path=/dev/tpm0 \
--rng egd,backend_host=127.0.0.1,backend_service=8000,backend_type=udp,backend_mode=bind,backend_connect_host=foo,backend_connect_service=708 \
--panic iobase=0x506 \
""", "singleton-config-2")


# Device testing #1

c.add_compare(""" \
--vcpus 4,cores=1 \
--cpu none \
\
--disk %(EXISTUPPER)s,cache=writeback,io=threads,perms=sh,serial=WD-WMAP9A966149,boot_order=2 \
--disk %(NEWIMG1)s,sparse=false,size=.001,perms=ro,error_policy=enospace,discard=unmap \
--disk device=cdrom,bus=sata,read_bytes_sec=1,read_iops_sec=2,total_bytes_sec=10,total_iops_sec=20,write_bytes_sec=5,write_iops_sec=6 \
--disk size=1 \
--disk %(BLOCKVOL)s \
--disk /dev/default-pool/iso-vol \
--disk /dev/default-pool/iso-vol,format=qcow2 \
--disk source_pool=rbd-ceph,source_volume=some-rbd-vol,size=.1 \
--disk pool=rbd-ceph,size=.1 \
--disk source_protocol=http,source_host_name=example.com,source_host_port=8000,source_name=/path/to/my/file \
--disk source_protocol=nbd,source_host_transport=unix,source_host_socket=/tmp/socket,bus=scsi \
--disk gluster://192.168.1.100/test-volume/some/dir/test-gluster.qcow2 \
--disk qemu+nbd:///var/foo/bar/socket,bus=usb,removable=on \
--disk path=http://[1:2:3:4:1:2:3:4]:5522/my/path?query=foo \
--disk vol=gluster-pool/test-gluster.raw,startup_policy=optional \
--disk %(DIR)s,device=floppy \
\
--network user,mac=12:34:56:78:11:22,portgroup=foo \
--network bridge=foobar,model=virtio,driver_name=qemu,driver_queues=3 \
--network bridge=ovsbr,virtualport_type=openvswitch,virtualport_profileid=demo,virtualport_interfaceid=09b11c53-8b5c-4eeb-8f00-d84eaa0aaa3b \
--network type=direct,source=eth5,source_mode=vepa,target=mytap12,virtualport_type=802.1Qbg,virtualport_managerid=12,virtualport_typeid=1193046,virtualport_typeidversion=1,virtualport_instanceid=09b11c53-8b5c-4eeb-8f00-d84eaa0aaa3b,boot_order=1 \
\
--graphics sdl \
--graphics spice,keymap=none \
--graphics vnc,port=5950,listen=1.2.3.4,keymap=ja,password=foo \
--graphics spice,port=5950,tlsport=5950,listen=1.2.3.4,keymap=ja \
--graphics spice,image_compression=foo,streaming_mode=bar,clipboard_copypaste=yes,mouse_mode=client,filetransfer_enable=on \
\
--controller usb,model=ich9-ehci1,address=0:0:4.7,index=0 \
--controller usb,model=ich9-uhci1,address=0:0:4.0,index=0,master=0 \
--controller usb,model=ich9-uhci2,address=0:0:4.1,index=0,master=2 \
--controller usb,model=ich9-uhci3,address=0:0:4.2,index=0,master=4 \
\
--input keyboard,bus=usb \
--input type=tablet \
\
--serial tcp,host=:2222,mode=bind,protocol=telnet \
--parallel udp,host=0.0.0.0:1234,bind_host=127.0.0.1:1234 \
--parallel unix,path=/tmp/foo-socket \
--channel pty,target_type=guestfwd,target_address=127.0.0.1:10000 \
--channel pty,target_type=virtio,name=org.linux-kvm.port1 \
--console pty,target_type=virtio \
--channel spicevmc \
\
--hostdev net_00_1c_25_10_b1_e4,boot_order=4,rom_bar=off \
--host-device usb_device_781_5151_2004453082054CA1BEEE \
--host-device 001.003 \
--hostdev 15:0.1 \
--host-device 2:15:0.2 \
--hostdev 0:15:0.3 \
--host-device 0x0781:0x5151,driver_name=vfio \
--host-device 04b3:4485 \
--host-device pci_8086_2829_scsi_host_scsi_device_lun0 \
--hostdev usb_5_20 --hostdev usb_5_21 \
\

--filesystem /source,/target \
--filesystem template_name,/,type=template,mode=passthrough \
--filesystem type=file,source=/tmp/somefile.img,target=/mount/point,accessmode=squash \
\
--soundhw default \
--sound ac97 \
\
--video cirrus \
--video model=qxl \
\
--smartcard passthrough,type=spicevmc \
--smartcard type=host \
\
--redirdev usb,type=spicevmc \
--redirdev usb,type=tcp,server=localhost:4000 \
--redirdev usb,type=tcp,server=127.0.0.1:4002,boot_order=3 \
\
--rng egd,backend_host=127.0.0.1,backend_service=8000,backend_type=tcp \
\
--panic iobase=507 \
""", "many-devices", compare_check=support.SUPPORT_CONN_VMPORT)



####################################################
# CPU/RAM/numa and other singleton VM config tests #
####################################################

c = vinst.add_category("cpuram", "--hvm --nographics --noautoconsole --nodisks --pxe")
c.add_valid("--vcpus 4 --cpuset=1,3-5,")  # Cpuset with trailing comma
c.add_valid("--vcpus 4 --cpuset=auto")  # cpuset=auto but caps doesn't support it
c.add_valid("--ram 4000000")  # Ram overcommit
c.add_valid("--vcpus sockets=2,threads=2")  # Topology only
c.add_valid("--cpu somemodel")  # Simple --cpu
c.add_valid("--security label=foobar.label,relabel=yes")  # --security implicit static
c.add_valid("--security label=foobar.label,a1,z2,b3,type=static,relabel=no")  # static with commas 1
c.add_valid("--security label=foobar.label,a1,z2,b3")  # --security static with commas 2
c.add_compare("--connect %(URI-TEST-DEFAULT)s --cpuset auto --vcpus 2", "cpuset-auto")  # --cpuset=auto actually works
c.add_invalid("--vcpus 32 --cpuset=969-1000")  # Bogus cpuset
c.add_invalid("--vcpus 32 --cpuset=autofoo")  # Bogus cpuset
c.add_invalid("--clock foo_tickpolicy=merge")  # Unknown timer
c.add_invalid("--security foobar")  # Busted --security



########################
# Storage provisioning #
########################

c = vinst.add_category("storage", "--pxe --nographics --noautoconsole --hvm")
c.add_valid("--disk path=%(EXISTIMG1)s")  # Existing disk, no extra options
c.add_valid("--disk pool=%(POOL)s,size=.0001 --disk pool=%(POOL)s,size=.0001")  # Create 2 volumes in a pool
c.add_valid("--disk vol=%(POOL)s/%(VOL)s")  # Existing volume
c.add_valid("--disk path=%(EXISTIMG1)s --disk path=%(EXISTIMG1)s --disk path=%(EXISTIMG1)s --disk path=%(EXISTIMG1)s,device=cdrom")  # 3 IDE and CD
c.add_valid("--disk path=%(EXISTIMG1)s,bus=scsi --disk path=%(EXISTIMG1)s,bus=scsi --disk path=%(EXISTIMG1)s,bus=scsi --disk path=%(EXISTIMG1)s,bus=scsi --disk path=%(EXISTIMG1)s,bus=scsi --disk path=%(EXISTIMG1)s,bus=scsi --disk path=%(EXISTIMG1)s,bus=scsi --disk path=%(EXISTIMG1)s,bus=scsi --disk path=%(EXISTIMG1)s,bus=scsi --disk path=%(EXISTIMG1)s,bus=scsi --disk path=%(EXISTIMG1)s,bus=scsi --disk path=%(EXISTIMG1)s,bus=scsi --disk path=%(EXISTIMG1)s,bus=scsi --disk path=%(EXISTIMG1)s,bus=scsi --disk path=%(EXISTIMG1)s,bus=scsi --disk path=%(EXISTIMG1)s,bus=scsi --disk path=%(EXISTIMG1)s,bus=scsi")  # > 16 scsi disks
c.add_valid("--disk path=%(NEWIMG1)s,format=raw,size=.0000001")  # Unmanaged file using format 'raw'
c.add_valid("--disk path=%(MANAGEDNEW1)s,format=raw,size=.0000001")  # Managed file using format raw
c.add_valid("--disk path=%(MANAGEDNEW1)s,format=qcow2,size=.0000001")  # Managed file using format qcow2
c.add_valid("--disk %(EXISTIMG1)s")  # Not specifying path=
c.add_valid("--disk %(NEWIMG1)s,format=raw,size=.0000001")  # Not specifying path= but creating storage
c.add_valid("--disk %(COLLIDE)s --check path_in_use=off")  # Colliding storage with --check
c.add_valid("--disk %(COLLIDE)s --force")  # Colliding storage with --force
c.add_valid("--disk %(SHARE)s,perms=sh")  # Colliding shareable storage
c.add_valid("--disk path=%(EXISTIMG1)s,device=cdrom --disk path=%(EXISTIMG1)s,device=cdrom")  # Two IDE cds
c.add_valid("--disk %(EXISTIMG1)s,driver_name=qemu,driver_type=qcow2")  # Driver name and type options
c.add_valid("--disk /dev/zero")  # Referencing a local unmanaged /dev node
c.add_valid("--disk pool=default,size=.00001")  # Building 'default' pool
c.add_valid("--disk %(AUTOMANAGEIMG)s,size=.1")  # autocreate the pool
c.add_valid("--disk %(NEWIMG1)s,sparse=true,size=100000000 --check disk_size=off")  # Don't warn about fully allocated file exceeding disk space
c.add_invalid("--file %(NEWIMG1)s --file-size 100000 --nonsparse")  # Nonexisting file, size too big
c.add_invalid("--file %(NEWIMG1)s --file-size 100000")  # Huge file, sparse, but no prompting
c.add_invalid("--file %(NEWIMG1)s")  # Nonexisting file, no size
c.add_invalid("--file %(EXISTIMG1)s --file %(EXISTIMG1)s --file %(EXISTIMG1)s --file %(EXISTIMG1)s --file %(EXISTIMG1)s")  # Too many IDE
c.add_invalid("--disk pool=foopool,size=.0001")  # Specify a nonexistent pool
c.add_invalid("--disk vol=%(POOL)s/foovol")  # Specify a nonexistent volume
c.add_invalid("--disk pool=%(POOL)s")  # Specify a pool with no size
c.add_invalid("--disk path=%(EXISTIMG1)s,perms=ro,size=.0001,cache=FOOBAR")  # Unknown cache type
c.add_invalid("--disk path=/dev/foo/bar/baz,format=qcow2,size=.0000001")  # Unmanaged file using non-raw format
c.add_invalid("--disk path=%(MANAGEDDISKNEW1)s,format=raw,size=.0000001")  # Managed disk using any format
c.add_invalid("--disk %(NEWIMG1)s")  # Not specifying path= and non existent storage w/ no size
c.add_invalid("--disk %(NEWIMG1)s,sparse=true,size=100000000000")  # Fail if fully allocated file would exceed disk space
c.add_invalid("--disk %(COLLIDE)s")  # Colliding storage without --force
c.add_invalid("--disk %(COLLIDE)s --prompt")  # Colliding storage with --prompt should still fail
c.add_invalid("--disk /dev/default-pool/backingl3.img")  # Colliding storage via backing store
c.add_invalid("--disk %(DIR)s,device=cdrom")  # Dir without floppy
c.add_invalid("--disk %(EXISTIMG1)s,driver_name=foobar,driver_type=foobaz")  # Unknown driver name and type options (as of 1.0.0)
c.add_invalid("--disk source_pool=rbd-ceph,source_volume=vol1")  # Collision with existing VM, via source pool/volume
c.add_invalid("--disk size=1 --security model=foo,type=bar")  # Libvirt will error on the invalid security params, which should trigger the code path to clean up the disk images we created.



################################################
# Invalid devices that hit virtinst code paths #
################################################

c = vinst.add_category("invalid-devices", "--noautoconsole --nodisks --pxe")
c.add_invalid("--host-device 1d6b:2")  # multiple USB devices with identical vendorId and productId
c.add_invalid("--host-device pci_8086_2850_scsi_host_scsi_host")  # Unsupported hostdev type
c.add_invalid("--host-device foobarhostdev")  # Unknown hostdev
c.add_invalid("--host-device 300:400")  # Parseable hostdev, but unknown digits
c.add_invalid("--graphics vnc,keymap=ZZZ")  # Invalid keymap
c.add_invalid("--graphics vnc,port=-50")  # Invalid port
c.add_invalid("--graphics spice,tlsport=5")  # Invalid port
c.add_invalid("--serial unix")  # Unix with no path
c.add_invalid("--serial null,path=/tmp/foo")  # Path where it doesn't belong
c.add_invalid("--channel pty,target_type=guestfwd")  # --channel guestfwd without target_address
c.add_invalid("--boot uefi")  # URI doesn't support UEFI bits
c.add_invalid("--connect %(URI-KVM)s --boot uefi,arch=ppc64")  # unsupported arch for UEFI



########################
# Install option tests #
########################

c = vinst.add_category("nodisk-install", "--nographics --noautoconsole --nodisks")
c.add_valid("--hvm --cdrom %(EXISTIMG1)s")  # Simple cdrom install
c.add_valid("--wait 0 --os-variant winxp --cdrom %(EXISTIMG1)s")  # Windows (2 stage) install
c.add_valid("--pxe --virt-type test")  # Explicit virt-type
c.add_valid("--arch i686 --pxe")  # Explicity fullvirt + arch
c.add_valid("--arch i486 --pxe")  # Convert i*86 -> i686
c.add_valid("--location %(TREEDIR)s")  # Directory tree URL install
c.add_valid("--location %(TREEDIR)s --initrd-inject virt-install --extra-args ks=file:/virt-install")  # initrd-inject
c.add_valid("--hvm --location %(TREEDIR)s --extra-args console=ttyS0")  # Directory tree URL install with extra-args
c.add_valid("--hvm --cdrom %(TREEDIR)s")  # Directory tree CDROM install
c.add_valid("--paravirt --location %(TREEDIR)s")  # Paravirt location
c.add_valid("--paravirt --location %(TREEDIR)s --os-variant none")  # Paravirt location with --os-variant none
c.add_valid("--location %(TREEDIR)s --os-variant fedora12")  # URL install with manual os-variant
c.add_valid("--cdrom %(EXISTIMG2)s --os-variant win2k3 --wait 0")  # HVM windows install with disk
c.add_valid("--cdrom %(EXISTIMG2)s --os-variant win2k3 --wait 0 --print-step 3")  # HVM windows install, print 3rd stage XML
c.add_valid("--pxe --autostart")  # --autostart flag
c.add_compare("--pxe --print-step all", "simple-pxe")  # Diskless PXE install
c.add_invalid("--pxe --virt-type bogus")  # Bogus virt-type
c.add_invalid("--pxe --arch bogus")  # Bogus arch
c.add_invalid("--paravirt --pxe")  # PXE w/ paravirt
c.add_invalid("--import")  # Import with no disks
c.add_invalid("--livecd")  # LiveCD with no media
c.add_invalid("--pxe --os-variant farrrrrrrge")  # Bogus --os-variant
c.add_invalid("--pxe --boot menu=foobar")
c.add_invalid("--cdrom %(EXISTIMG1)s --extra-args console=ttyS0")  # cdrom fail w/ extra-args
c.add_invalid("--hvm --boot kernel=%(TREEDIR)s/pxeboot/vmlinuz,initrd=%(TREEDIR)s/pxeboot/initrd.img,kernel_args='foo bar' --initrd-inject virt-install")  # initrd-inject with manual kernel/initrd

c = vinst.add_category("single-disk-install", "--nographics --noautoconsole --disk %(EXISTIMG1)s")
c.add_valid("--hvm --import")  # FV Import install
c.add_valid("--hvm --import --prompt --force")  # Working scenario w/ prompt shouldn't ask anything
c.add_valid("--paravirt --import")  # PV Import install
c.add_valid("--paravirt --print-xml")  # print single XML, implied import install
c.add_compare("--cdrom %(EXISTIMG2)s --os-variant win2k3 --wait 0 --vcpus cores=4 --controller usb,model=none", "w2k3-cdrom")  # HVM windows install with disk
c.add_invalid("--paravirt --import --print-xml 2")  # PV Import install, no second XML step

c = vinst.add_category("misc-install", "--nographics --noautoconsole")
c.add_valid("--disk path=%(EXISTIMG1)s,device=cdrom")  # Implied cdrom install
c.add_compare("", "noargs-fail", auto_printarg=False)  # No arguments
c.add_valid("--panic help --disk=?")  # Make sure introspection doesn't blow up
c.add_invalid("--hvm --nodisks --pxe foobar")  # Positional arguments error
c.add_invalid("--nodisks --pxe --name test")  # Colliding name



#############################
# Remote URI specific tests #
#############################

c = vinst.add_category("remote", "--connect %(URI-TEST-REMOTE)s --nographics --noautoconsole")
c.add_valid("--nodisks --pxe")  # Simple pxe nodisks
c.add_valid("--pxe --disk /foo/bar/baz,size=.01")  # Creating any random path on the remote host
c.add_valid("--pxe --disk /dev/zde")  # /dev file that we just pass through to the remote VM
c.add_invalid("--pxe --disk /foo/bar/baz")  # File that doesn't exist after auto storage setup
c.add_invalid("--nodisks --location /tmp")  # Use of --location
c.add_invalid("--file /foo/bar/baz --pxe")  # Trying to use unmanaged storage without size argument



###########################
# QEMU/KVM specific tests #
###########################

c = vinst.add_category("kvm", "--connect %(URI-KVM)s --noautoconsole", compare_check=support.SUPPORT_CONN_VMPORT)
c.add_compare("--os-variant fedora-unknown --file %(EXISTIMG1)s --location %(TREEDIR)s --extra-args console=ttyS0 --cpu host --channel none --console none --sound none --redirdev none", "kvm-f14-url")  # Fedora Directory tree URL install with extra-args
c.add_compare("--test-media-detection %(TREEDIR)s", "test-url-detection")  # --test-media-detection
c.add_compare("--os-variant fedora20 --disk %(NEWIMG1)s,size=.01,format=vmdk --location %(TREEDIR)s --extra-args console=ttyS0 --quiet", "quiet-url")  # Quiet URL install should make no noise
c.add_compare("--cdrom %(EXISTIMG2)s --file %(EXISTIMG1)s --os-variant win2k3 --wait 0 --sound --controller usb", "kvm-win2k3-cdrom")  # HVM windows install with disk
c.add_compare("--os-variant ubuntusaucy --nodisks --boot cdrom --virt-type qemu --cpu Penryn", "qemu-plain")  # plain qemu
c.add_compare("--os-variant fedora20 --nodisks --boot network --nographics --arch i686", "qemu-32-on-64")  # 32 on 64

# armv7l tests
c.add_compare("--arch armv7l --machine vexpress-a9 --boot kernel=/f19-arm.kernel,initrd=/f19-arm.initrd,dtb=/f19-arm.dtb,extra_args=\"console=ttyAMA0 rw root=/dev/mmcblk0p3\" --disk %(EXISTIMG1)s --nographics", "arm-vexpress-plain")
c.add_compare("--arch armv7l --machine vexpress-a15 --boot kernel=/f19-arm.kernel,initrd=/f19-arm.initrd,dtb=/f19-arm.dtb,kernel_args=\"console=ttyAMA0,1234 rw root=/dev/vda3\",extra_args=foo --disk %(EXISTIMG1)s --nographics --os-variant fedora19", "arm-vexpress-f19")
c.add_compare("--arch armv7l --machine virt --boot kernel=/f19-arm.kernel,initrd=/f19-arm.initrd,kernel_args=\"console=ttyAMA0,1234 rw root=/dev/vda3\",extra_args=foo --disk %(EXISTIMG1)s --nographics --os-variant fedora20", "arm-virt-f20")
c.add_compare("--arch armv7l --boot kernel=/f19-arm.kernel,initrd=/f19-arm.initrd,kernel_args=\"console=ttyAMA0,1234 rw root=/dev/vda3\",extra_args=foo --disk %(EXISTIMG1)s --os-variant fedora20", "arm-defaultmach-f20")
c.add_compare("--connect %(URI-KVM-ARMV7L)s --disk %(EXISTIMG1)s --import --os-variant fedora20", "arm-kvm-import")

# aarch64 tests
c.add_compare("--arch aarch64 --machine virt --boot kernel=/f19-arm.kernel,initrd=/f19-arm.initrd,kernel_args=\"console=ttyAMA0,1234 rw root=/dev/vda3\",extra_args=foo --disk %(EXISTIMG1)s", "aarch64-machvirt")
c.add_compare("--arch aarch64 --boot kernel=/f19-arm.kernel,initrd=/f19-arm.initrd,kernel_args=\"console=ttyAMA0,1234 rw root=/dev/vda3\",extra_args=foo --disk %(EXISTIMG1)s", "aarch64-machdefault")
c.add_compare("--arch aarch64 --cdrom %(EXISTIMG2)s --boot loader=CODE.fd,nvram_template=VARS.fd --disk %(EXISTIMG1)s --cpu none --events on_crash=preserve,on_reboot=destroy,on_poweroff=restart", "aarch64-cdrom")
c.add_compare("--connect %(URI-KVM-AARCH64)s --disk %(EXISTIMG1)s --import --os-variant fedora21", "aarch64-kvm-import")

# ppc64 tests
c.add_compare("--arch ppc64 --machine pseries --boot network --disk %(EXISTIMG1)s --os-variant fedora20 --network none", "ppc64-pseries-f20")
c.add_compare("--arch ppc64 --boot network --disk %(EXISTIMG1)s --os-variant fedora20 --network none", "ppc64-machdefault-f20")
c.add_compare("--connect %(URI-KVM-PPC64LE)s --import --disk %(EXISTIMG1)s --os-variant fedora20", "ppc64le-kvm-import")

# s390x tests
c.add_compare("--arch s390x --machine s390-ccw-virtio --connect %(URI-KVM-S390X)s --boot kernel=/kernel.img,initrd=/initrd.img --disk %(EXISTIMG1)s --disk %(EXISTIMG3)s,device=cdrom --os-variant fedora21", "s390x-cdrom")
c.add_compare("--arch s390x --machine s390-ccw-virtio --connect %(URI-KVM-S390X-KVMIBM)s --boot kernel=/kernel.img,initrd=/initrd.img --disk %(EXISTIMG1)s --disk %(EXISTIMG3)s,device=cdrom --os-variant fedora21 --watchdog diag288,action=reset", "s390x-cdrom-KVMIBM")

# qemu:///session tests
c.add_compare("--connect %(URI-KVM-SESSION)s --disk size=8 --os-variant fedora21 --cdrom %(EXISTIMG1)s", "kvm-session-defaults")

# misc KVM config tests
c.add_compare("--disk none --location %(EXISTIMG3)s --nonetworks", "location-iso")  # Using --location iso mounting
c.add_compare("--disk %(EXISTIMG1)s --pxe --os-variant rhel6.4", "kvm-rhel6")  # RHEL6 defaults
c.add_compare("--disk %(EXISTIMG1)s --pxe --os-variant rhel7.0", "kvm-rhel7")  # RHEL7 defaults
c.add_compare("--disk %(EXISTIMG1)s --pxe --os-variant centos7.0", "kvm-centos7")  # Centos 7 defaults
c.add_compare("--os-variant win7 --cdrom %(EXISTIMG2)s --boot loader_type=pflash,loader=CODE.fd,nvram_template=VARS.fd --disk %(EXISTIMG1)s", "win7-uefi")  # no HYPER-V with UEFI
c.add_compare("--machine q35 --cdrom %(EXISTIMG2)s --disk %(EXISTIMG1)s", "q35-defaults")  # proper q35 disk defaults
c.add_compare("--disk size=20 --os-variant solaris10", "solaris10-defaults")  # test solaris OS defaults
c.add_compare("--connect %(URI-KVM-REMOTE)s --import --disk %(EXISTIMG1)s --os-variant fedora21 --pm suspend_to_disk=yes", "f21-kvm-remote")

c.add_valid("--connect %(URI-KVM-NODOMCAPS)s --arch aarch64 --nodisks --pxe")  # attempt to default to aarch64 UEFI, but it fails, but should only print warnings
c.add_invalid("--disk none --boot network --machine foobar")  # Unknown machine type
c.add_invalid("--nodisks --boot network --arch mips --virt-type kvm")  # Invalid domain type for arch
c.add_invalid("--nodisks --boot network --paravirt --arch mips")  # Invalid arch/virt combo


######################
# LXC specific tests #
######################

c = vinst.add_category("lxc", "--connect %(URI-LXC)s --noautoconsole --name foolxc --memory 64")
c.add_compare("", "default")
c.add_compare("--filesystem /source,/", "fs-default")
c.add_compare("--init /usr/bin/httpd", "manual-init")



######################
# Xen specific tests #
######################

c = vinst.add_category("xen", "--connect %(URI-XEN)s --noautoconsole")
c.add_valid("--disk %(EXISTIMG1)s --location %(TREEDIR)s --paravirt --graphics none")  # Xen PV install headless
c.add_compare("--disk %(EXISTIMG1)s --import", "xen-default")  # Xen default
c.add_compare("--disk %(EXISTIMG1)s --location %(TREEDIR)s --paravirt", "xen-pv")  # Xen PV
c.add_compare("--disk %(BLOCKVOL)s --cdrom %(EXISTIMG1)s --livecd --hvm", "xen-hvm")  # Xen HVM



#####################################
# Device option back compat testing #
#####################################

c = vinst.add_category("device-back-compat", "--nodisks --pxe --noautoconsole")
c.add_valid("--sdl")  # SDL
c.add_valid("--vnc --keymap ja --vncport 5950 --vnclisten 1.2.3.4")  # VNC w/ lots of options
c.add_valid("--sound")  # --sound with no option back compat
c.add_valid("--mac 22:22:33:44:55:AF")  # Just a macaddr
c.add_valid("--bridge mybr0 --mac 22:22:33:44:55:AF")  # Old bridge w/ mac
c.add_valid("--network bridge:mybr0,model=e1000")  # --network bridge:
c.add_valid("--network network:default --mac RANDOM")  # VirtualNetwork with a random macaddr
c.add_valid("--vnc --keymap=local")  # --keymap local
c.add_invalid("--nonetworks")  # no networks
c.add_invalid("--graphics vnc --vnclisten 1.2.3.4")  # mixing old and new
c.add_invalid("--network=FOO")  # Nonexistent network
c.add_invalid("--mac 1234")  # Invalid mac
c.add_invalid("--network user --bridge foo0")  # Mixing bridge and network
c.add_invalid("--mac 22:22:33:12:34:AB")  # Colliding macaddr

c = vinst.add_category("storage-back-compat", "--pxe --noautoconsole")
c.add_valid("--file %(EXISTIMG1)s --nonsparse --file-size 4")  # Existing file, other opts
c.add_valid("--file %(EXISTIMG1)s")  # Existing file, no opts
c.add_valid("--file %(EXISTIMG1)s --file %(EXISTIMG1)s")  # Multiple existing files
c.add_valid("--file %(NEWIMG1)s --file-size .00001 --nonsparse")  # Nonexistent file




##################
# virt-xml tests #
##################

vixml = App("virt-xml")
c = vixml.add_category("misc", "")
c.add_valid("--help")  # basic --help test
c.add_valid("--sound=? --tpm=?")  # basic introspection test
c.add_invalid("test --edit --hostdev driver_name=vfio")  # Guest has no hostdev to edit
c.add_invalid("test --edit --cpu host-passthrough --boot hd,network")  # Specified more than 1 option
c.add_invalid("test --edit")  # specified no edit option
c.add_invalid("test --edit 2 --cpu host-passthrough")  # specifing --edit number where it doesn't make sense
c.add_invalid("test-for-virtxml --edit 5 --tpm /dev/tpm")  # device edit out of range
c.add_invalid("test-for-virtxml --add-device --host-device 0x0781:0x5151 --update")  # test driver doesn't support attachdevice...
c.add_invalid("test-for-virtxml --remove-device --host-device 1 --update")  # test driver doesn't support detachdevice...
c.add_invalid("test-for-virtxml --edit --graphics password=foo --update")  # test driver doesn't support updatdevice...
c.add_invalid("--build-xml --memory 10,maxmemory=20")  # building XML for option that doesn't support it
c.add_compare("test --print-xml --edit --vcpus 7", "print-xml")  # test --print-xml
c.add_compare("--edit --cpu host-passthrough", "stdin-edit", input_file=(xmldir + "/virtxml-stdin-edit.xml"))  # stdin test
c.add_compare("--build-xml --cpu pentium3,+x2apic", "build-cpu")
c.add_compare("--build-xml --tpm /dev/tpm", "build-tpm")
c.add_compare("--build-xml --blkiotune weight=100,device_path=/dev/sdf,device_weight=200", "build-blkiotune")
c.add_compare("--build-xml --idmap uid_start=0,uid_target=1000,uid_count=10,gid_start=0,gid_target=1000,gid_count=10", "build-idmap")
c.add_compare("test --edit --boot network,cdrom", "edit-bootorder")
c.add_compare("--confirm test --edit --cpu host-passthrough", "prompt-response")


c = vixml.add_category("simple edit diff", "test-for-virtxml --edit --print-diff --define", compare_check=support.SUPPORT_CONN_INPUT_KEYBOARD)
c.add_compare("""--metadata name=foo-my-new-name,uuid=12345678-12F4-1234-1234-123456789AFA,description="hey this is my
new
very,very=new desc\\\'",title="This is my,funky=new title" """, "edit-simple-metadata")
c.add_compare("--events on_poweroff=destroy,on_reboot=restart,on_crash=preserve", "edit-simple-events")
c.add_compare("--memory 500,maxmemory=1000,hugepages=off", "edit-simple-memory")
c.add_compare("--vcpus 10,maxvcpus=20,cores=5,sockets=4,threads=1", "edit-simple-vcpus")
c.add_compare("--cpu model=pentium2,+x2apic,forbid=pbe", "edit-simple-cpu")
c.add_compare("--numatune 1-5,7,mode=strict", "edit-simple-numatune")
c.add_compare("--blkiotune weight=500,device_path=/dev/sdf,device_weight=600", "edit-simple-blkiotune")
c.add_compare("--idmap uid_start=0,uid_target=2000,uid_count=30,gid_start=0,gid_target=3000,gid_count=40", "edit-simple-idmap", compare_check=support.SUPPORT_CONN_LOADER_ROM)
c.add_compare("--boot loader=foo.bar,useserial=on,init=/bin/bash", "edit-simple-boot", compare_check=support.SUPPORT_CONN_LOADER_ROM)
c.add_compare("--security label=foo,bar,baz,UNKNOWN=val,relabel=on", "edit-simple-security")
c.add_compare("--features eoi=on,hyperv_relaxed=off,acpi=", "edit-simple-features")
c.add_compare("--clock offset=localtime,hpet_present=yes,kvmclock_present=no,rtc_tickpolicy=merge", "edit-simple-clock")
c.add_compare("--pm suspend_to_mem=yes,suspend_to_disk=no", "edit-simple-pm")
c.add_compare("--disk /dev/zero,perms=ro,startup_policy=optional", "edit-simple-disk")
c.add_compare("--disk path=", "edit-simple-disk-remove-path")
c.add_compare("--network source=br0,type=bridge,model=virtio,mac=", "edit-simple-network")
c.add_compare("--graphics tlsport=5902,keymap=ja", "edit-simple-graphics")
c.add_compare("--controller index=15,model=lsilogic", "edit-simple-controller")
c.add_compare("--smartcard type=spicevmc", "edit-simple-smartcard")
c.add_compare("--redirdev type=spicevmc,server=example.com:12345", "edit-simple-redirdev")
c.add_compare("--tpm path=/dev/tpm", "edit-simple-tpm")
c.add_compare("--rng rate_bytes=3333,rate_period=4444", "edit-simple-rng")
c.add_compare("--watchdog action=reset", "edit-simple-watchdog")
c.add_compare("--memballoon model=none", "edit-simple-memballoon")
c.add_compare("--serial pty", "edit-simple-serial")
c.add_compare("--parallel unix,path=/some/other/log", "edit-simple-parallel")
c.add_compare("--channel null", "edit-simple-channel")
c.add_compare("--console name=foo.bar.baz", "edit-simple-console")
c.add_compare("--filesystem /1/2/3,/4/5/6,mode=mapped", "edit-simple-filesystem")
c.add_compare("--video cirrus", "edit-simple-video", compare_check=support.SUPPORT_CONN_VIDEO_NEW_RAM_OUTPUT)
c.add_compare("--sound pcspk", "edit-simple-soundhw")
c.add_compare("--host-device 0x0781:0x5151,driver_name=vfio", "edit-simple-host-device")

c = vixml.add_category("edit selection", "test-for-virtxml --print-diff --define", compare_check=support.SUPPORT_CONN_INPUT_KEYBOARD)
c.add_invalid("--edit target=vvv --disk /dev/null")  # no match found
c.add_compare("--edit 3 --sound pcspk", "edit-pos-num", compare_check=support.SUPPORT_CONN_VIDEO_NEW_RAM_OUTPUT)
c.add_compare("--edit -1 --video qxl", "edit-neg-num", compare_check=support.SUPPORT_CONN_VIDEO_NEW_RAM_OUTPUT)
c.add_compare("--edit all --host-device driver_name=vfio", "edit-all")
c.add_compare("--edit ich6 --sound pcspk", "edit-select-sound-model", compare_check=support.SUPPORT_CONN_VIDEO_NEW_RAM_OUTPUT)
c.add_compare("--edit target=hda --disk /dev/null", "edit-select-disk-target")
c.add_compare("--edit /tmp/foobar2 --disk shareable=off,readonly=on", "edit-select-disk-path")
c.add_compare("--edit mac=00:11:7f:33:44:55 --network target=nic55", "edit-select-network-mac")

c = vixml.add_category("edit clear", "test-for-virtxml --print-diff --define", compare_check=support.SUPPORT_CONN_INPUT_KEYBOARD)
c.add_invalid("--edit --memory 200,clearxml=yes")  # clear isn't wired up for memory
c.add_compare("--edit --disk path=/foo/bar,target=fda,bus=fdc,device=floppy,clearxml=yes", "edit-clear-disk")
c.add_compare("--edit --cpu host-passthrough,clearxml=yes", "edit-clear-cpu")
c.add_compare("--edit --clock offset=utc,clearxml=yes", "edit-clear-clock")

c = vixml.add_category("add/rm devices", "test-for-virtxml --print-diff --define", compare_check=support.SUPPORT_CONN_INPUT_KEYBOARD)
c.add_valid("--add-device --security model=dac")  # --add-device works for seclabel
c.add_invalid("--add-device --pm suspend_to_disk=yes")  # --add-device without a device
c.add_invalid("--remove-device --clock utc")  # --remove-device without a dev
c.add_compare("--add-device --host-device net_00_1c_25_10_b1_e4", "add-host-device")
c.add_compare("--add-device --sound pcspk", "add-sound")
c.add_compare("--add-device --disk %(EXISTIMG1)s,bus=virtio,target=vdf", "add-disk-basic")
c.add_compare("--add-device --disk %(EXISTIMG1)s", "add-disk-notarget")  # filling in acceptable target
c.add_compare("--add-device --disk %(NEWIMG1)s,size=.01", "add-disk-create-storage")
c.add_compare("--remove-device --sound ich6", "remove-sound-model", compare_check=support.SUPPORT_CONN_VIDEO_NEW_RAM_OUTPUT)
c.add_compare("--remove-device --disk 3", "remove-disk-index")
c.add_compare("--remove-device --disk /dev/null", "remove-disk-path")
c.add_compare("--remove-device --video all", "remove-video-all", compare_check=support.SUPPORT_CONN_VIDEO_NEW_RAM_OUTPUT)
c.add_compare("--remove-device --host-device 0x04b3:0x4485", "remove-hostdev-name", compare_check=support.SUPPORT_CONN_VIDEO_NEW_RAM_OUTPUT)




####################
# virt-clone tests #
####################

vclon = App("virt-clone")
c = vclon.add_category("remote", "--connect %(URI-TEST-REMOTE)s")
c.add_valid("-o test --auto-clone")  # Auto flag, no storage
c.add_valid("--original-xml %(CLONE_STORAGE_XML)s --auto-clone")  # Auto flag w/ managed storage
c.add_invalid("--original-xml %(CLONE_DISK_XML)s --auto-clone")  # Auto flag w/ local storage, which is invalid for remote connection


c = vclon.add_category("misc", "")
c.add_compare("--connect %(URI-KVM)s -o test-for-clone --auto-clone --clone-running", "clone-auto1", compare_check=support.SUPPORT_CONN_LOADER_ROM)
c.add_compare("-o test-clone-simple --name newvm --auto-clone --clone-running", "clone-auto2", compare_check=support.SUPPORT_CONN_LOADER_ROM)
c.add_valid("-o test --auto-clone")  # Auto flag, no storage
c.add_valid("--original-xml %(CLONE_STORAGE_XML)s --auto-clone")  # Auto flag w/ managed storage
c.add_valid("--original-xml %(CLONE_DISK_XML)s --auto-clone")  # Auto flag w/ local storage
c.add_valid("-o test-for-clone --auto-clone --clone-running")  # Auto flag, actual VM, skip state check
c.add_valid("-o test-clone-simple -n newvm --preserve-data --file %(EXISTIMG1)s --clone-running")  # Preserve data shouldn't complain about existing volume
c.add_valid("-n clonetest --original-xml %(CLONE_DISK_XML)s --file %(EXISTIMG3)s --file %(EXISTIMG4)s --check path_exists=off")  # Skip existing file check
c.add_invalid("--auto-clone")  # Just the auto flag
c.add_invalid("-o test-for-clone --auto-clone")
c.add_invalid("-o test-clone-simple -n newvm --file %(EXISTIMG1)s --clone-running")  # Should complain about overwriting existing file


c = vclon.add_category("general", "-n clonetest")
c.add_valid("-o test")  # Nodisk guest
c.add_valid("-o test --file %(NEWCLONEIMG1)s --file %(NEWCLONEIMG2)s")  # Nodisk, but with spurious files passed
c.add_valid("-o test --file %(NEWCLONEIMG1)s --file %(NEWCLONEIMG2)s --prompt")  # Working scenario w/ prompt shouldn't ask anything
c.add_valid("--original-xml %(CLONE_DISK_XML)s --file %(NEWCLONEIMG1)s --file %(NEWCLONEIMG2)s")  # XML File with 2 disks
c.add_valid("--original-xml %(CLONE_DISK_XML)s --file virt-install --file %(EXISTIMG1)s --preserve")  # XML w/ disks, overwriting existing files with --preserve
c.add_valid("--original-xml %(CLONE_DISK_XML)s --file %(NEWCLONEIMG1)s --file %(NEWCLONEIMG2)s --file %(NEWCLONEIMG3)s --force-copy=hdc")  # XML w/ disks, force copy a readonly target
c.add_valid("--original-xml %(CLONE_DISK_XML)s --file %(NEWCLONEIMG1)s --file %(NEWCLONEIMG2)s --force-copy=fda")  # XML w/ disks, force copy a target with no media
c.add_valid("--original-xml %(CLONE_STORAGE_XML)s --file %(MANAGEDNEW1)s")  # XML w/ managed storage, specify managed path
c.add_valid("--original-xml %(CLONE_NOEXIST_XML)s --file %(EXISTIMG1)s --preserve")  # XML w/ managed storage, specify managed path across pools# Libvirt test driver doesn't support cloning across pools# XML w/ non-existent storage, with --preserve
c.add_valid("-o test -n test-for-clone --replace")  # Overwriting existing VM
c.add_invalid("-o test foobar")  # Positional arguments error
c.add_invalid("-o idontexist")  # Non-existent vm name
c.add_invalid("-o idontexist --auto-clone")  # Non-existent vm name with auto flag,
c.add_invalid("-o test -n test")  # Colliding new name
c.add_invalid("--original-xml %(CLONE_DISK_XML)s")  # XML file with several disks, but non specified
c.add_invalid("--original-xml %(CLONE_DISK_XML)s --file virt-install --file %(EXISTIMG1)s")  # XML w/ disks, overwriting existing files with no --preserve
c.add_invalid("--original-xml %(CLONE_DISK_XML)s --file %(NEWCLONEIMG1)s --file %(NEWCLONEIMG2)s --force-copy=hdc")  # XML w/ disks, force copy but not enough disks passed
c.add_invalid("--original-xml %(CLONE_STORAGE_XML)s --file /tmp/clonevol")  # XML w/ managed storage, specify unmanaged path (should fail)
c.add_invalid("--original-xml %(CLONE_NOEXIST_XML)s --file %(EXISTIMG1)s")  # XML w/ non-existent storage, WITHOUT --preserve




######################
# virt-convert tests #
######################

vconv = App("virt-convert")
c = vconv.add_category("misc", "--connect %(URI-KVM)s --dry", compare_check=support.SUPPORT_CONN_VMPORT)
c.add_invalid("%(VMX_IMG1)s --input-format foo")  # invalid input format
c.add_invalid("%(EXISTIMG1)s")  # invalid input file

c.add_compare("%(VMX_IMG1)s --disk-format qcow2 --print-xml", "vmx-compare")
c.add_compare("%(OVF_IMG1)s --disk-format none --destination /tmp --print-xml", "ovf-compare")




#########################
# Test runner functions #
#########################

newidx = 0
curtest = 0


def setup():
    """
    Create initial test files/dirs
    """
    for i in exist_files:
        os.system("touch %s" % i)


def cleanup():
    """
    Cleanup temporary files used for testing
    """
    for i in clean_files:
        os.system("chmod 777 %s > /dev/null 2>&1" % i)
        os.system("rm -rf %s > /dev/null 2>&1" % i)


class CLITests(unittest.TestCase):
    def setUp(self):
        global curtest
        curtest += 1
        # Only run this for first test
        if curtest == 1:
            setup()

    def tearDown(self):
        # Only run this on the last test
        if curtest == newidx:
            cleanup()


def maketest(cmd):
    def cmdtemplate(self, _cmdobj):
        _cmdobj.run(self)
    return lambda s: cmdtemplate(s, cmd)

_cmdlist = []
_cmdlist += vinst.cmds
_cmdlist += vclon.cmds
_cmdlist += vconv.cmds
_cmdlist += vixml.cmds

for _cmd in _cmdlist:
    newidx += 1
    _name = "testCLI"
    _name += "%s%.4d" % (os.path.basename(_cmd.app.replace("-", "")), newidx)
    setattr(CLITests, _name, maketest(_cmd))

atexit.register(cleanup)
