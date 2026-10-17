"""Descriptor-only decoder subprocess. Never imports the web app or its secrets."""
import ctypes
import errno
import io
import json
import os
import resource
import socket
import sys
import warnings
from PIL import Image,ImageOps,ImageCms
import pillow_heif

def sandbox():
    libc=ctypes.CDLL(None,use_errno=True)
    lib=ctypes.CDLL('libseccomp.so.2',use_errno=True)
    lib.seccomp_init.argtypes=[ctypes.c_uint32];lib.seccomp_init.restype=ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
    lib.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
    class ArgCompare(ctypes.Structure):
        _fields_=[('arg',ctypes.c_uint),('op',ctypes.c_uint),('mask',ctypes.c_uint64),('value',ctypes.c_uint64)]
    lib.seccomp_rule_add_array.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint,ctypes.POINTER(ArgCompare)]
    lib.seccomp_load.argtypes=[ctypes.c_void_p];lib.seccomp_release.argtypes=[ctypes.c_void_p]
    ctx=lib.seccomp_init(0x7fff0000)
    if not ctx or libc.prctl(38,1,0,0,0)!=0:raise RuntimeError('Sandbox unavailable')
    try:
        for name in ('open','openat','openat2','creat','socket','socketpair','connect','bind','listen','accept','accept4','execve','execveat','fork','vfork','ptrace','process_vm_readv','process_vm_writev','pidfd_getfd','io_uring_setup','io_uring_enter','io_uring_register','mount','umount2','bpf','memfd_create','link','linkat','symlink','symlinkat','rename','renameat','renameat2','unlink','unlinkat'):
            number=lib.seccomp_syscall_resolve_name(name.encode())
            if number>=0 and lib.seccomp_rule_add(ctx,0x50000|errno.EPERM,number,0)!=0:raise RuntimeError('Sandbox rule failed')
        # libheif's tiled decoder uses pthreads even with its worker count set to
        # zero. Threads inherit this filter and the same descriptor-only memory.
        # Reject every clone lacking CLONE_THREAD; clone3 is unavailable so libc
        # falls back to the inspectable clone flags. No child process can start.
        number=lib.seccomp_syscall_resolve_name(b'clone3')
        if number>=0 and lib.seccomp_rule_add(ctx,0x50000|errno.ENOSYS,number,0)!=0:raise RuntimeError('Sandbox rule failed')
        no_thread=ArgCompare(0,7,0x10000,0)
        if lib.seccomp_rule_add_array(ctx,0x50000|errno.EPERM,lib.seccomp_syscall_resolve_name(b'clone'),1,ctypes.byref(no_thread))!=0:raise RuntimeError('Sandbox rule failed')
        if lib.seccomp_load(ctx)!=0:raise RuntimeError('Sandbox load failed')
    finally:lib.seccomp_release(ctx)

def decode(source,destination,profile):
    with Image.open(source) as image:
        if image.format not in ('JPEG','PNG','WEBP','HEIF') or getattr(image,'n_frames',1)!=1:raise ValueError('unsupported')
        width,height=image.size
        if width*height>50000000 or max(width,height)>16384:raise MemoryError()
        if image.format=='HEIF' and pillow_heif.get_file_mimetype(source) not in ('image/heic','image/heif'):raise ValueError('unsupported')
        image.draft('RGB',(4096,4096))
        image.load()
        # Shrink before orientation/profile conversion to bound peak resident memory.
        image.thumbnail((2048,2048),Image.Resampling.LANCZOS,reducing_gap=3)
        oriented=ImageOps.exif_transpose(image)
        icc=image.info.get('icc_profile')
        if icc:
            try:oriented=ImageCms.profileToProfile(oriented,ImageCms.ImageCmsProfile(io.BytesIO(icc)),profile,outputMode='RGB')
            except (ValueError,TypeError,ImageCms.PyCMSError):raise ValueError('invalid profile') from None
        if oriented.mode in ('RGBA','LA') or 'transparency' in oriented.info:
            rgba=oriented.convert('RGBA');rgb=Image.new('RGB',rgba.size,'white');rgb.paste(rgba,mask=rgba.getchannel('A'));rgba.close()
        else:rgb=oriented.convert('RGB')
        clean=Image.new('RGB',rgb.size);clean.paste(rgb);rgb.close()
        clean.save(destination,format='JPEG',quality=85,exif=b'',icc_profile=None)
        destination.flush();os.fsync(destination.fileno())
        length=destination.tell()
        if length>4*1024*1024:raise MemoryError()
        destination.seek(0)
        with Image.open(destination) as verified:
            verified.load()
            if verified.getexif() or any(k in verified.info for k in ('icc_profile','xmp','comment','exif')):raise ValueError('metadata remains')
        return dict(width=clean.width,height=clean.height,bytes=length,mediaType='image/jpeg')

def main():
    # pthread takes its default stack size from RLIMIT_STACK at process startup.
    # Hosted builders can inherit 16 MiB instead of 8 MiB; tiled HEIC threads then
    # exhaust the same 160 MiB address-space cap. Re-exec before reading any image
    # with a bounded stack; retain any stricter inherited limit and all open FDs.
    stack_soft,stack_hard=resource.getrlimit(resource.RLIMIT_STACK)
    stack_limit=8*1024*1024
    if stack_soft==resource.RLIM_INFINITY or stack_soft>stack_limit:
        resource.setrlimit(resource.RLIMIT_STACK,(stack_limit,stack_hard))
        os.execv(sys.executable,[sys.executable,'-B',__file__,*sys.argv[1:]])
    # All image plugins and colour libraries are loaded before restricting syscalls.
    pillow_heif.register_heif_opener(decode_threads=0,thumbnails=False,depth_images=False,aux_images=False)
    Image.init();profile=ImageCms.createProfile('sRGB')
    Image.MAX_IMAGE_PIXELS=50000000
    warnings.simplefilter('error',Image.DecompressionBombWarning)
    source=os.fdopen(int(sys.argv[1]),'rb');destination=os.fdopen(int(sys.argv[2]),'w+b');result=os.fdopen(int(sys.argv[3]),'w')
    resource.setrlimit(resource.RLIMIT_AS,(160*1024*1024,160*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(15,15))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(4*1024*1024+4096,4*1024*1024+4096))
    try:
        sandbox()
        # A fail-closed self-check runs for every conversion; it cannot read a key.
        denied_file=denied_socket=denied_process=False
        try:os.open('/data/secret.key',os.O_RDONLY)
        except PermissionError:denied_file=True
        try:socket.socket()
        except PermissionError:denied_socket=True
        try:os.fork()
        except PermissionError:denied_process=True
        if not denied_file or not denied_socket or not denied_process:raise RuntimeError('Sandbox self-check failed')
        value=decode(source,destination,profile)
        value.update(sandboxFileDenied=True,sandboxNetworkDenied=True,sandboxProcessDenied=True,peakRssKiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (MemoryError,Image.DecompressionBombError,Image.DecompressionBombWarning):value={'error':'IMAGE_LIMIT_EXCEEDED'}
    except Exception:value={'error':'IMAGE_INVALID'}
    json.dump(value,result);result.flush()

if __name__=='__main__':main()
