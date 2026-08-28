// Sem console no Windows em release — a decisão de plataforma alvo é Windows.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    solis_lib::run()
}
