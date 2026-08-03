//! Flat ABI over the vendored pixel snapper, compiled to `wasm32-wasip1`.

use std::alloc::{alloc, dealloc, Layout};
use std::ptr::addr_of_mut;

static mut RESULT: Vec<u8> = Vec::new();
static mut ERROR: Vec<u8> = Vec::new();

#[no_mangle]
pub extern "C" fn ssc_alloc(len: usize) -> *mut u8 {
    if len == 0 {
        return std::ptr::null_mut();
    }
    unsafe { alloc(Layout::from_size_align_unchecked(len, 1)) }
}

#[no_mangle]
pub extern "C" fn ssc_dealloc(ptr: *mut u8, len: usize) {
    if ptr.is_null() || len == 0 {
        return;
    }
    unsafe { dealloc(ptr, Layout::from_size_align_unchecked(len, 1)) }
}

#[no_mangle]
pub extern "C" fn ssc_snap(
    in_ptr: *const u8,
    in_len: usize,
    k_colors: u32,
    pixel_size_override: f64,
    pal_ptr: *const u8,
    pal_len: usize,
) -> i32 {
    // `from_raw_parts` is unsound on a null pointer even for a zero length, and a caller
    // that alloc'd nothing hands us exactly that.
    if in_ptr.is_null() || in_len == 0 {
        return fail("no input bytes");
    }
    let palette_owned = if pal_ptr.is_null() || pal_len == 0 {
        None
    } else {
        let raw = unsafe { std::slice::from_raw_parts(pal_ptr, pal_len) };
        match std::str::from_utf8(raw) {
            Ok(s) => Some(s.to_string()),
            Err(_) => return fail("palette is not valid UTF-8"),
        }
    };
    let input = unsafe { std::slice::from_raw_parts(in_ptr, in_len) };
    let k = if k_colors == 0 { None } else { Some(k_colors) };
    let px = if pixel_size_override > 0.0 {
        Some(pixel_size_override)
    } else {
        None
    };

    match spritefusion_pixel_snapper::process_image_wasi(input, k, px, palette_owned.as_deref()) {
        Ok(bytes) => unsafe {
            *addr_of_mut!(RESULT) = bytes;
            *addr_of_mut!(ERROR) = Vec::new();
            0
        },
        Err(e) => fail(&e.to_string()),
    }
}

fn fail(message: &str) -> i32 {
    unsafe {
        *addr_of_mut!(RESULT) = Vec::new();
        *addr_of_mut!(ERROR) = message.as_bytes().to_vec();
    }
    1
}

#[no_mangle]
pub extern "C" fn ssc_result_ptr() -> *const u8 {
    unsafe { (*addr_of_mut!(RESULT)).as_ptr() }
}

#[no_mangle]
pub extern "C" fn ssc_result_len() -> usize {
    unsafe { (*addr_of_mut!(RESULT)).len() }
}

#[no_mangle]
pub extern "C" fn ssc_error_ptr() -> *const u8 {
    unsafe { (*addr_of_mut!(ERROR)).as_ptr() }
}

#[no_mangle]
pub extern "C" fn ssc_error_len() -> usize {
    unsafe { (*addr_of_mut!(ERROR)).len() }
}
