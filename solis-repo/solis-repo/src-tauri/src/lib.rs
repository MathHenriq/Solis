use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // Fechar a janela principal fecha o Solis. A ilha (a janela da chamada)
        // fica escondida e, sozinha, segurava o app aberto: o Matheus fechou o
        // Solis e o processo seguiu vivo, sem a escuta nem nada que servisse
        // (18/11/2026). A escuta e a conversa moram na principal.
        .on_window_event(|janela, evento| {
            if janela.label() == "main" && matches!(evento, tauri::WindowEvent::Destroyed) {
                janela.app_handle().exit(0);
            }
        })
        .run(tauri::generate_context!())
        .expect("erro ao iniciar o Solis");
}
