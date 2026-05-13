# flet_app.py — PashuMitra AI (Standalone — No Server Needed)
# ✅ AI logic is built-in. Just run: python flet_app.py

import flet as ft


# ---------------------------------------------------------------------------
# Built-in AI engine — no backend server required
# ---------------------------------------------------------------------------

def get_ai_response(text: str) -> str:
    q = text.lower().strip()

    if any(k in q for k in ["stomach", "bloat", "pet", "afara", "gas", "phool", "aafra", "pet fool", "pet dard"]):
        return (
            "🐄 Pet Phoolna / Bloat (Afara)\n\n"
            "🌿 Gharelu Upay:\n"
            "  • Hing + ajwain ka paste banayein\n"
            "  • Pashu ko 20 minute chalayein\n"
            "  • Abhi pani pilana band karein\n\n"
            "💊 Dawai: Ruminal stimulant (vet se lein)\n"
            "📍 Najdiki dukaan: ~2 km\n"
            "🚨 2 ghante mein theek na ho to vet bulayein"
        )

    if any(k in q for k in ["doodh", "milk", "mastitis", "thaan", "dudh", "not giving milk", "doodh nahi"]):
        return (
            "🐄 Doodh Ki Samasya / Mastitis\n\n"
            "🌿 Gharelu Upay:\n"
            "  • Thaan ko garam paani se saaf karein\n"
            "  • Sarson tel se malish karein\n"
            "  • Saaf jagah rakhein\n\n"
            "💊 Dawai: Vet se antibiotic prescription zaruri\n"
            "📍 Krishi Kendra: ~3 km\n"
            "🚨 24 ghante mein vet se milein"
        )

    if any(k in q for k in ["bukhar", "fever", "jwar", "tap", "garmi", "temperature", "garam"]):
        return (
            "🐄 Bukhar / Fever\n\n"
            "🌿 Gharelu Upay:\n"
            "  • Thanda paani pilayein\n"
            "  • Chhaya mein rakhein\n"
            "  • Mathe par thanda kapda rakhein\n\n"
            "💊 Dawai: Paracetamol — sirf vet ki dose mein\n"
            "📍 Govt PHC: ~5 km\n"
            "🚨 101F se zyada ho to emergency hai"
        )

    if any(k in q for k in ["diarrhea", "loose motion", "daast", "potty", "loose", "pakhana"]):
        return (
            "🐄 Daast / Diarrhea\n\n"
            "🌿 Gharelu Upay:\n"
            "  • ORS solution pilayein\n"
            "  • Hara chaara kam karein\n"
            "  • Saaf paani zyada pilayein\n\n"
            "💊 Dawai: Electrolyte powder (pashu wala)\n"
            "📍 Pashu Aushadhalay: ~2 km\n"
            "🚨 Khoon aa raha ho to turant vet bulayein"
        )

    if any(k in q for k in ["wound", "injury", "chot", "ghav", "cut", "khoon", "blood", "zakhm"]):
        return (
            "🐄 Chot / Ghav\n\n"
            "🌿 Gharelu Upay:\n"
            "  • Saaf paani se dhoyein\n"
            "  • Haldi + sarson tel lagayein\n"
            "  • Kapde se dhak dein\n\n"
            "💊 Dawai: Antiseptic spray (Povidone Iodine)\n"
            "📍 Medical store: ~1 km\n"
            "🚨 Gehri chot ho to turant vet"
        )

    if any(k in q for k in ["khansi", "cough", "saans", "breathe", "naak", "nose", "khasi"]):
        return (
            "🐄 Khansi / Saans Ki Takleef\n\n"
            "🌿 Gharelu Upay:\n"
            "  • Tulsi + adrak ka kadha pilayein\n"
            "  • Dhoop mein rakhein\n"
            "  • Nami se bachayein\n\n"
            "💊 Dawai: Vet se antibiotic lein\n"
            "📍 Najdiki dukaan: ~4 km\n"
            "🚨 Saans lene mein bahut takleef ho to emergency"
        )

    if any(k in q for k in ["khujli", "itch", "rash", "skin", "daad", "baal", "chamdi"]):
        return (
            "🐄 Chamdi Ki Bimari / Skin Problem\n\n"
            "🌿 Gharelu Upay:\n"
            "  • Neem ke patte ubaal ke nahilayein\n"
            "  • Haldi + sarson tel lagayein\n\n"
            "💊 Dawai: Ivermectin injection (vet se)\n"
            "📍 Najdiki dukaan: ~3 km\n"
            "🚨 Emergency nahi"
        )

    if any(k in q for k in ["khana", "eating", "nahi kha", "not eating", "bhukh", "chaara", "feed"]):
        return (
            "🐄 Khana Na Khana\n\n"
            "🌿 Gharelu Upay:\n"
            "  • Hing + ajwain dein\n"
            "  • Taza hara chaara dein\n"
            "  • Paani zaroor pilayein\n\n"
            "💊 Dawai: Appetite stimulant (vet se)\n"
            "📍 Najdiki dukaan: ~2 km\n"
            "🚨 2 din se kuch na khaya ho to vet zaruri"
        )

    return (
        f"🐄 Aapki baat samajh aayi: \"{text}\"\n\n"
        "✅ Abhi ke liye:\n"
        "  • Saaf paani pilate rahein\n"
        "  • Aaram karne dein\n"
        "  • 24 ghante monitor karein\n\n"
        "💡 In mein se koi likho:\n"
        "   bukhar, pet dard, doodh, khansi,\n"
        "   daast, chot, khujli, khana nahi khana"
    )


# ---------------------------------------------------------------------------
# Flet UI
# ---------------------------------------------------------------------------

def main(page: ft.Page) -> None:
    page.title = "PashuMitra AI"
    page.bgcolor = "#F0F4F0"
    page.padding = 0
    page.window.width = 420
    page.window.height = 700

    chat = ft.ListView(
        expand=True,
        spacing=8,
        padding=ft.padding.symmetric(horizontal=16, vertical=12),
        auto_scroll=True,
    )

    def add_bubble(text: str, is_user: bool) -> None:
        bubble = ft.Container(
            content=ft.Text(
                text,
                size=13,
                color="#FFFFFF" if is_user else "#1B5E20",
                selectable=True,
            ),
            bgcolor="#25D366" if is_user else "#FFFFFF",
            border_radius=ft.border_radius.only(
                top_left=16, top_right=16,
                bottom_left=0 if is_user else 16,
                bottom_right=16 if is_user else 0,
            ),
            padding=ft.padding.symmetric(horizontal=14, vertical=10),
            margin=ft.margin.only(
                left=60 if is_user else 0,
                right=0 if is_user else 60,
            ),
        )
        chat.controls.append(bubble)
        page.update()

    def on_send(e) -> None:
        text = (input_field.value or "").strip()
        if not text:
            return
        add_bubble(f"👨‍🌾 {text}", is_user=True)
        input_field.value = ""
        # input_field.focus()
        page.update()
        response = get_ai_response(text)
        add_bubble(response, is_user=False)

    input_field = ft.TextField(
        hint_text="Gaay/bhains ki takleef likhein...",
        expand=True,
        border_radius=24,
        border_color="#C8E6C9",
        focused_border_color="#25D366",
        bgcolor="#FFFFFF",
        content_padding=ft.padding.symmetric(horizontal=16, vertical=10),
        text_size=13,
        on_submit=on_send,
    )

    send_btn = ft.IconButton(
        icon=ft.Icons.SEND_ROUNDED,
        icon_color="#FFFFFF",
        bgcolor="#25D366",
        icon_size=20,
        tooltip="Bhejein",
        on_click=on_send,
        style=ft.ButtonStyle(shape=ft.CircleBorder()),
    )

    # Welcome bubble
    chat.controls.append(
        ft.Container(
            content=ft.Text(
                "🐄 Namaste! Main PashuMitra AI hoon.\n\n"
                "Apni gaay, bhains, ya bakri ki koi bhi\n"
                "takleef batayein — main turant jawab dunga! 🌿",
                size=13,
                color="#1B5E20",
                text_align=ft.TextAlign.CENTER,
            ),
            bgcolor="#E8F5E9",
            border_radius=12,
            padding=16,
            margin=ft.margin.only(bottom=8),
        )
    )

    page.add(
        ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text("🐄 PashuMitra AI Vet 🌿", size=17,
                            weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor="#2E7D32",
            padding=ft.padding.symmetric(vertical=14),
            alignment=ft.Alignment(0, 0),
        ),
        ft.Container(content=chat, expand=True, bgcolor="#F0F4F0"),
        ft.Container(
            content=ft.Row(
                controls=[input_field, send_btn],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            bgcolor="#FFFFFF",
        ),
    )


if __name__ == "__main__":
    ft.app(main)