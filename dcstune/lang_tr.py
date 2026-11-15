"""Turkish. Keys are the English sentences exactly as the program writes them (see i18n.py).
DCS itself has no Turkish menus, so the names of DCS settings keep their English name in brackets:
the player has to find them in DCS's own options screen."""

TR = {
    # ---- page: fixed texts (data-t in ui.html) ------------------------------------------------
    "ui.subtitle": "Monitörde (2D) uçuş içindir. VR ayarları değiştirilmez.",
    "ui.reading": "Bilgisayarınız ve DCS ayarlarınız okunuyor...",
    "ui.profile-pick-title": "Hangi DCS ayar klasörünün puanlanıp optimize edileceği",
    "ui.headset": "VR gözlüğünüz:",
    "ui.headset-pick-title": "Araç hangi VR gözlüğünü kullandığınızı anlayamadı; puan kartının onun çözünürlüğünü ve yenileme hızını kullanması için seçin",
    "ui.download": "İndir",
    "ui.setup-title": "DCS'in nerede olduğunu gösterin",
    "ui.browse": "Gözat...",
    "ui.use-folder": "Bu klasörü kullan",
    "ui.consent-title": "Bu aracın gelişmesine yardım eder misiniz? (isteğe bağlı)",
    "ui.consent-ask": "Araç, her testin sonucunu bu aracın yapımcısı Fox3'e gönderebilir mi? Gönderim <b>anonimdir</b>.",
    "ui.consent-sent": "<b>Gönderilenler:</b> işlemciniz, ekran kartınız ve sürücüsü, belleğiniz, monitör çözünürlüğünüz, DCS sürümü, varsa VR gözlüğü modeli ve VR yazılımı, DCS grafik ve VR ayarlarınız, ölçülen kare hızları ve öneriyi uygulayıp uygulamadığınız ya da geri alıp almadığınız.",
    "ui.consent-notsent": "<b>Gönderilmeyenler:</b> adınız, Windows ya da DCS hesabınız, pilot adınız, klasör adları, seri numaraları, ekran görüntüleri ve kontroller. Her teste yalnızca rastgele bir numara verilir; size ya da bilgisayarınıza ait bir numara yoktur. Sonuçlar internet adresiniz olmadan saklanır.",
    "ui.consent-why": "<b>Ne işe yarar:</b> araç, her ayarın sizin donanımınızda neye mal olduğunu tahmin eder. Birçok farklı bilgisayardan ve VR gözlüğünden gelen gerçek sonuçlar, bu tahminleri ve önerileri herkes için daha iyi yapar.",
    "ui.consent-audit": "Her testten sonra aynı bilgiler rapor klasörüne <b>audit.json</b> olarak kaydedilir; böylece tam olarak neyin gönderildiğini okuyabilirsiniz. Bize daha fazlasını anlatmak isterseniz sonuca yorum ekleyebilirsiniz.",
    "ui.consent-no": "Hayır derseniz hiçbir şey gönderilmez ve araç tamamen aynı şekilde çalışır. Cevabınızı istediğiniz zaman Ayarlar sekmesinden değiştirebilirsiniz.",
    "ui.share-yes": "Evet, anonim sonuçları gönder",
    "ui.share-no": "Hayır, hiçbir şey gönderme",
    "ui.tab-score": "Puan kartı",
    "ui.tab-test": "Test",
    "ui.tab-report": "Rapor",
    "ui.tab-settings": "Ayarlar",
    "ui.cancel": "Vazgeç",
    "ui.no-report": "Henüz bir test sonucu yok. Test sekmesinden bir test başlatın.",
    "ui.settings-folders": "DCS klasörleri",
    "ui.folder-profile": "Ayarlarınız (Saved Games)",
    "ui.folder-install": "DCS World kurulumu",
    "ui.change-install": "Değiştir...",
    "ui.settings-lang": "Dil",
    "ui.settings-sharing": "Anonim sonuçlar",
    "ui.settings-about": "Hakkında",
    "ui.overall": "Genel",
    "ui.machine": "DCS için bilgisayarınız",
    "ui.fit": "Şu anki ayarlarınız",
    "ui.mode-legend": "Sizin için en önemlisi hangisi?",
    "ui.mode-smooth": "<b>Akıcılık</b> &mdash; görüntü daha sade olsa bile ekranınızın gösterebildiği en yüksek kare hızı (rekabetçi uçuş için).",
    "ui.mode-balanced": "<b>Dengeli</b> &mdash; hiç takılmaz ve harika görünür: en kötü anlarda en az 60 FPS ve mümkün olan en iyi görüntünün büyük kısmı. Önerilen.",
    "ui.mode-quality": "<b>Kalite</b> &mdash; en kötü anlarda 60 FPS'i korurken bilgisayarınızın gösterebildiği en güzel görüntü.",
    "ui.quick": "Test et ve optimize et (10-20 dk)",
    "ui.full": "Kapsamlı test (35-60 dk)",
    "ui.undo": "Son değişikliği geri al",
    "ui.leave-alone": "Test, DCS'i birkaç kez kendiliğinden başlatır ve kapatır. Çalışırken bilgisayara dokunmayın. Ayarlarınız her testten sonra geri konur; Uygula'ya basana kadar hiçbir şey değişmez.",
    "ui.about-title": "Testler ne yapar ve ne kadar sürer?",
    "ui.about-1": "Her test DCS'i birkaç kez kendiliğinden başlatır ve kapatır. Önce ekran kartını kullanan diğer programları kapatın (oyunlar, video işleme, yapay zekâ araçları); kart meşgulse test başlamayı reddeder.",
    "ui.about-2": "Her seferinde bilgisayar Kafkasya haritasında üç kısa sahne uçar (şehir üzerinden geçiş, havaalanı apronu, bulut katmanı) ve her kare tek tek ölçülür.",
    "ui.about-3": "<b>Test et ve optimize et</b>: 2-5 başlatma, genellikle 10-20 dakika. Ayarlarınızı ölçer, sonra bir öneriyi test edip düzeltir.",
    "ui.about-4": "<b>Kapsamlı test</b>: yaklaşık 10 başlatma, genellikle 35-60 dakika. Ayrıca her pahalı ayarın sizin bilgisayarınızda neye mal olduğunu ölçer; çoğu, yalnızca görevi yeniden başlatan tek bir uzun DCS oturumunda ölçülür.",
    "ui.about-5": "Hedef, en kötü anlarda monitörünüzün yenileme hızıdır (en fazla 120 FPS); daha yavaş bilgisayarlarda 90, 72 ya da 60'a iner.",
    "ui.about-6": "Çözünürlük, dikey eşitleme (V-Sync), VR, kontroller ve ses asla değiştirilmez. Ayar dosyanız her başlatmadan sonra geri yüklenir.",
    "ui.testing": "Test ediliyor",
    "ui.faillog-title": "Bunu düzeltmemize yardım edin",
    "ui.faillog-send": "Bu hata kaydını geliştiriciye gönder",
    "ui.faillog-show": "Neyin gönderileceğini göster",
    "ui.result": "Test sonucu",
    "ui.apply": "Bu ayarları uygula",
    "ui.open-report": "Kaydedilen raporu aç",
    "ui.fb-title": "Bu sonuç hakkında daha fazlasını anlatın (isteğe bağlı, anonim)",
    "ui.fb-ask": "Önerilen ayarlarla uçtuktan sonra, eski ayarlarınıza göre nasıl hissettiriyor?",
    "ui.feel-better": "Daha iyi",
    "ui.feel-same": "Aynı",
    "ui.feel-worse": "Daha kötü",
    "ui.fb-placeholder": "Başka her şey: ne ters gitti, ne tuhaf göründü, hangi uçağı ya da haritayı uçuyorsunuz. Lütfen isim ve diğer kişisel bilgileri yazmayın.",
    "ui.fb-send": "Geri bildirim gönder",
    "ui.hud-toggle": "Küçük HUD",
    "ui.hud-toggle-title": "Uçarken ya da testi izlerken her zaman üstte duran küçük telemetri ekranı",
    "ui.telemetry-title": "Canlı sistem telemetrisi",
    "ui.radar-title": "Kokpit yetenek radarı ve denge tablosu",
    "ui.tel-cpu": "İşlemci (CPU)",
    "ui.tel-gpu": "Ekran kartı (GPU)",
    "ui.tel-vram": "Ekran belleği (VRAM)",
    "ui.tel-ram": "Sistem belleği (RAM)",

    # ---- page: texts its script builds --------------------------------------------------------
    "DCS: Standby": "DCS: Beklemede",
    "DCS: Running": "DCS: Çalışıyor",
    "DCS: Loading mission (trial {0}/{1})...": "DCS: Görev yükleniyor (deneme {0}/{1})...",
    "DCS: Settling textures ({0}%)...": "DCS: Dokular yerleşiyor (%{0})...",
    "DCS: Scene {0}/{1} ({2}) \u2014 {3}%": "DCS: Sahne {0}/{1} ({2}) \u2014 %{3}",
    "Live in DCS: {0} FPS ({1} ms)": "DCS anlık: {0} FPS ({1} ms)",
    "Something went wrong": "Bir şeyler ters gitti",
    "This report and its screenshots are saved in Saved Games\\{0}\\DCS Graphics Optimizer Reports\\{1}. You can keep or share that folder.":
        "Bu rapor ve ekran görüntüleri Saved Games (Kayıtlı Oyunlar)\\{0}\\DCS Graphics Optimizer Reports\\{1} klasörüne kaydedildi. Bu klasörü saklayabilir ya da paylaşabilirsiniz.",
    "Where is DCS World installed?": "DCS World nereye kurulu?",
    "Where are your DCS settings?": "DCS ayarlarınız nerede?",
    "for example E:\\DCS World": "örneğin E:\\DCS World",
    "for example E:\\Saved Games\\DCS": "örneğin E:\\Saved Games\\DCS",
    "Pick the main DCS World folder, the one that contains the bin folder. Steam: ...\\steamapps\\common\\DCSWorld.":
        "Ana DCS World klasörünü, yani içinde bin klasörü olanı seçin. Steam: ...\\steamapps\\common\\DCSWorld.",
    "Pick the DCS folder inside Saved Games, the one that contains Config\\options.lua. If it does not exist yet, start DCS once and close it.":
        "Saved Games (Kayıtlı Oyunlar) içindeki DCS klasörünü, yani içinde Config\\options.lua olanı seçin. Henüz yoksa DCS'i bir kez başlatıp kapatın.",
    "Change ({0} found)...": "Değiştir ({0} adet bulundu)...",
    "Change...": "Değiştir...",
    "Other folder...": "Başka klasör...",
    "Pick the DCS folder inside Saved Games that DCS really uses (it contains Config\\options.lua).":
        "Saved Games (Kayıtlı Oyunlar) içinde DCS'in gerçekten kullandığı DCS klasörünü seçin (içinde Config\\options.lua bulunur).",
    "DCS settings not found yet": "DCS ayarları henüz bulunamadı",
    "DCS profile: ": "DCS profili: ",
    " / 100 \u2014 40% PC, 60% how well your settings use it": " / 100 \u2014 %40 bilgisayar, %60 ayarlarınızın onu ne kadar iyi kullandığı",
    "Your current settings ({0})": "Şu anki ayarlarınız ({0})",
    "An earlier test was interrupted, and you have changed DCS settings since then. Your current settings were kept. To go back to your settings from before that test, press Undo last change.":
        "Önceki bir test yarıda kesildi ve o zamandan beri DCS ayarlarını değiştirdiniz. Şu anki ayarlarınız korundu. O testten önceki ayarlarınıza dönmek için Son değişikliği geri al'a basın.",
    "An earlier test was interrupted. Your original settings have been restored.":
        "Önceki bir test yarıda kesildi. Özgün ayarlarınız geri yüklendi.",
    "VR test build. With VR on in your DCS profile, the test runs in your headset.":
        "VR test sürümü. DCS profilinizde VR açıksa test VR gözlüğünüzde çalışır.",
    "VR is switched on in this profile, so the scorecard is rated for your headset. The tests still run on the monitor and do not change VR settings yet.":
        "Bu profilde VR açık, bu yüzden puan kartı VR gözlüğünüze göre puanlanır. Testler hâlâ monitörde çalışır ve henüz VR ayarlarını değiştirmez.",
    "VR is switched on in this profile, so the test runs in your headset. Before you press start, connect the headset, open its own software (and Virtual Desktop or Link, if you use them), and put it on or keep it awake. DCS opens in the headset by itself and closes again when each part is done.":
        "Bu profilde VR açık, bu yüzden test VR gözlüğünüzde çalışır. Başlat'a basmadan önce gözlüğü bağlayın, kendi yazılımını (kullanıyorsanız Virtual Desktop ya da Link'i de) açın ve gözlüğü takın ya da uyanık tutun. DCS gözlükte kendiliğinden açılır ve her bölüm bitince kapanır.",
    "Not in the list / not sure": "Listede yok / emin değilim",
    "After each test the anonymous result is sent to Fox3, because you agreed to that; nothing else is sent.":
        "Kabul ettiğiniz için her testten sonra anonim sonuç Fox3'e gönderilir; başka hiçbir şey gönderilmez.",
    "Nothing is sent over the internet.": "İnternet üzerinden hiçbir şey gönderilmez.",
    " The full guide is in the project's User Guide.": " Ayrıntılı kılavuz, projenin Kullanım Kılavuzu'ndadır (User Guide, İngilizce).",
    "Stop sending": "Göndermeyi durdur",
    "Start sending anonymous results": "Anonim sonuçları göndermeye başla",
    "Anonymous results: ": "Anonim sonuçlar: ",
    "sent after each test.": "her testten sonra gönderiliyor.",
    "not sent.": "gönderilmiyor.",
    "You already sent feedback for this result. You can send more.":
        "Bu sonuç için zaten geri bildirim gönderdiniz. Daha fazlasını gönderebilirsiniz.",
    "Because you share test results, a short extract of DCS's log for this failure was sent to the developer (no names or folder paths). You can see it below.":
        "Test sonuçlarını paylaştığınız için, bu hataya ait DCS kaydının kısa bir özeti geliştiriciye gönderildi (isim ya da klasör yolu yok). Aşağıda görebilirsiniz.",
    "A short extract of DCS's log would show us why this failed. Your Windows user name and folder paths are removed. Nothing is sent unless you press the button.":
        "DCS kaydının kısa bir özeti, bunun neden başarısız olduğunu bize gösterir. Windows kullanıcı adınız ve klasör yolları çıkarılır. Düğmeye basmadığınız sürece hiçbir şey gönderilmez.",
    "Nothing was changed.": "Hiçbir şey değiştirilmedi.",
    "Version ": "Sürüm ",
    "A newer version is available: {0}. You have {1}. The newest one has the latest fixes.":
        "Daha yeni bir sürüm var: {0}. Sizdeki sürüm {1}. En yeni sürümde son düzeltmeler bulunur.",

    # ---- window: answers and errors (ui.py) ---------------------------------------------------
    "Headset set to {0}. The scorecard is now rated for it.": "VR gözlüğü {0} olarak ayarlandı. Puan kartı artık ona göre puanlanıyor.",
    "Headset cleared. The scorecard assumes a typical headset.": "VR gözlüğü seçimi kaldırıldı. Puan kartı tipik bir VR gözlüğü varsayıyor.",
    "There is no saved report yet. Run a test first.": "Henüz kaydedilmiş bir rapor yok. Önce bir test çalıştırın.",
    "Opened {0}": "Açıldı: {0}",
    "VR is switched on in this profile. This test runs on the monitor and your VR settings are left alone.":
        "Bu profilde VR açık. Bu test monitörde çalışır ve VR ayarlarınıza dokunulmaz.",
    "The report page could not be saved ({0}); the result is still shown here.":
        "Rapor sayfası kaydedilemedi ({0}); sonuç yine de burada gösteriliyor.",
    "Sent the anonymous result. Thank you.": "Anonim sonuç gönderildi. Teşekkürler.",
    "The anonymous result could not be sent (no connection?). Nothing else is affected.":
        "Anonim sonuç gönderilemedi (bağlantı yok mu?). Başka hiçbir şey etkilenmedi.",
    "Thank you. Anonymous results will be sent after each test.": "Teşekkürler. Anonim sonuçlar her testten sonra gönderilecek.",
    "Nothing will be sent. You can change this at the bottom of the window.":
        "Hiçbir şey gönderilmeyecek. Bunu pencerenin en altından değiştirebilirsiniz.",
    "Run a test first; feedback is attached to a test result.": "Önce bir test çalıştırın; geri bildirim bir test sonucuna eklenir.",
    "Anonymous sharing is switched off, so nothing was sent.": "Anonim paylaşım kapalı, bu yüzden hiçbir şey gönderilmedi.",
    "Choose better, same or worse, or write a comment.": "Daha iyi, aynı ya da daha kötü seçeneklerinden birini seçin ya da bir yorum yazın.",
    "Your feedback could not be sent (no connection?). Please try again later.":
        "Geri bildiriminiz gönderilemedi (bağlantı yok mu?). Lütfen daha sonra yeniden deneyin.",
    "Feedback sent. Thank you.": "Geri bildirim gönderildi. Teşekkürler.",
    "[vr] VR is switched on in this DCS profile, but this test ran on the monitor. DCS uses the same graphics settings in the headset, so settings that are smooth on the monitor can be much slower in VR (players have seen their headset frame rate halve). Apply them anyway?":
        "[vr] Bu DCS profilinde VR açık, ama bu test monitörde çalıştı. DCS, VR gözlüğünde de aynı grafik ayarlarını kullanır; bu yüzden monitörde akıcı olan ayarlar VR'da çok daha yavaş olabilir (oyuncular gözlükteki kare hızının yarıya indiğini gördü). Yine de uygulansın mı?",
    "Close DCS first. It overwrites its settings file when it exits.": "Önce DCS'i kapatın. DCS kapanırken ayar dosyasının üzerine yazar.",
    "There is no recommendation to apply yet.": "Henüz uygulanacak bir öneri yok.",
    "These settings are already applied.": "Bu ayarlar zaten uygulandı.",
    "Applied. Your previous settings are kept as {0}.": "Uygulandı. Önceki ayarlarınız {0} adıyla saklanıyor.",
    "No earlier settings saved by DCS Graphics Optimizer were found.": "DCS Graphics Optimizer'ın kaydettiği daha eski bir ayar bulunamadı.",
    "Your previous settings are back.": "Önceki ayarlarınız geri geldi.",
    "Choose Smoothness, Balanced or Quality.": "Akıcılık, Dengeli ya da Kalite seçeneklerinden birini seçin.",
    "A test is already running.": "Zaten bir test çalışıyor.",
    "There is no failure log to send.": "Gönderilecek bir hata kaydı yok.",
    "The failure log was already sent. Thank you.": "Hata kaydı zaten gönderildi. Teşekkürler.",
    "The failure log could not be sent (no connection?). Please try again later.":
        "Hata kaydı gönderilemedi (bağlantı yok mu?). Lütfen daha sonra yeniden deneyin.",
    "Failure log sent. Thank you, it helps us fix this.": "Hata kaydı gönderildi. Teşekkürler, bunu düzeltmemize yardımcı olur.",
    "A test is running; change the folder after it finishes.": "Bir test çalışıyor; klasörü test bittikten sonra değiştirin.",
    "Please answer the question about anonymous results first.": "Lütfen önce anonim sonuçlarla ilgili soruyu cevaplayın.",
    "A test is running; pick the headset after it finishes.": "Bir test çalışıyor; VR gözlüğünü test bittikten sonra seçin.",
    "Not a download page of this tool.": "Bu, aracın indirme sayfalarından biri değil.",
    "The download page is open in your browser. Close this window before running the new version.":
        "İndirme sayfası tarayıcınızda açıldı. Yeni sürümü çalıştırmadan önce bu pencereyi kapatın.",
    "The language was changed.": "Dil değiştirildi.",

    # ---- finding DCS (sysinfo.py) -------------------------------------------------------------
    "could not read hardware information: {0}": "donanım bilgisi okunamadı: {0}",
    "DCS.exe was not found in {0}. Pick the main DCS World folder, the one that contains the bin folder.":
        "{0} içinde DCS.exe bulunamadı. Ana DCS World klasörünü, yani içinde bin klasörü olanı seçin.",
    "Using DCS World in {0}.": "{0} konumundaki DCS World kullanılıyor.",
    "No DCS settings were found in {0}. Pick your Saved Games\\DCS folder, the one that contains Config\\options.lua.":
        "{0} içinde DCS ayarı bulunamadı. Saved Games (Kayıtlı Oyunlar)\\DCS klasörünüzü, yani içinde Config\\options.lua olanı seçin.",
    "Using the DCS settings in {0}.": "{0} konumundaki DCS ayarları kullanılıyor.",
    "Your DCS settings folder was not found (Saved Games\\DCS with Config\\options.lua). If you have started DCS on this PC before, use Browse to show where your Saved Games\\DCS folder is.":
        "DCS ayar klasörünüz bulunamadı (içinde Config\\options.lua olan Saved Games\\DCS). Bu bilgisayarda DCS'i daha önce başlattıysanız, Gözat ile Saved Games (Kayıtlı Oyunlar)\\DCS klasörünüzün yerini gösterin.",
    "DCS World was not found on this PC (searched the registry, Steam libraries and the usual folders on every drive). Use Browse to show where DCS World is installed.":
        "DCS World bu bilgisayarda bulunamadı (kayıt defteri, Steam kitaplıkları ve her sürücüdeki olağan klasörler arandı). Gözat ile DCS World'ün kurulu olduğu yeri gösterin.",
    "DCS.exe not found under {0}": "{0} altında DCS.exe bulunamadı",

    # ---- scorecard (rate.py) ------------------------------------------------------------------
    "Graphics card": "Ekran kartı",
    "Video memory": "Ekran belleği (VRAM)",
    "Processor": "İşlemci",
    "Processor speed": "İşlemci hızı",
    "Memory": "Bellek (RAM)",
    "{n0} / 100": "{n0} / 100",
    "{n0} / {n1} FPS": "{n0} / {n1} FPS",
    "Display": "Ekran",
    "VR headset": "VR gözlüğü",
    "VR software": "VR yazılımı",
    "DCS drive": "DCS sürücüsü",
    "DCS version": "DCS sürümü",
    "unknown": "bilinmiyor",
    "Hard disk": "Sabit disk (HDD)",
    "{0} ({n0} cores)": "{0} ({n0} çekirdek)",
    "{n0} x {n1} at {0} Hz": "{n0} x {n1}, {0} Hz",
    "{0}, render quality {n0}": "{0}, render kalitesi {n0}",
    "Pimax headset (model not known yet)": "Pimax gözlük (model henüz bilinmiyor)",
    "Headset not recognized": "VR gözlüğü tanınmadı",
    "{0} ({n0} x {n1} per eye)": "{0} (göz başına {n0} x {n1})",
    "estimated": "tahmini",
    "measured": "ölçüldü",
    "estimate": "tahmin",
    "rough estimate for VR, not measured": "VR için kaba tahmin, ölçülmedi",
    "estimated from your last test": "son testinize göre tahmin",
    "measured in your last test": "son testinizde ölçüldü",
    "headset": "VR gözlüğü",
    "display": "ekran",
    "Graphics card: {0} ({n0} GB) - {1}": "Ekran kartı: {0} ({n0} GB) - {1}",
    "{0} (not in our table yet, estimated)": "{0} (henüz tablomuzda yok, tahmini)",
    "Processor: {0} - {1} single-thread speed, which is what limits DCS (not in our table yet, estimated)":
        "İşlemci: {0} - tek çekirdek hızı {1}; DCS'i sınırlayan da budur (henüz tablomuzda yok, tahmini)",
    "Processor: {0} - {1} single-thread speed, which is what limits DCS":
        "İşlemci: {0} - tek çekirdek hızı {1}; DCS'i sınırlayan da budur",
    "Processor: {0} - {1} speed per core, which is what limits DCS, multithreaded version included (not in our table yet, estimated)":
        "İşlemci: {0} - çekirdek başına hızı {1}; çok iş parçacıklı (MT) sürüm dahil DCS'i sınırlayan da budur (henüz tablomuzda yok, tahmini)",
    "Processor: {0} - {1} speed per core, which is what limits DCS, multithreaded version included":
        "İşlemci: {0} - çekirdek başına hızı {1}; çok iş parçacıklı (MT) sürüm dahil DCS'i sınırlayan da budur",
    "Memory: {n0} GB - {0}": "Bellek: {n0} GB - {0}",
    "plenty": "fazlasıyla yeterli",
    "good": "iyi",
    "tight for DCS; 32 GB or more avoids stutter": "DCS için sınırda; 32 GB ya da fazlası takılmaları önler",
    "too little for DCS": "DCS için çok az",
    "top tier": "en üst seviye",
    "high end": "üst seviye",
    "mid range": "orta seviye",
    "entry level": "giriş seviyesi",
    "below DCS's comfortable minimum": "DCS'in rahat çalıştığı alt sınırın altında",
    "Frame rate dips to about {n0} FPS ({0}), just short of the {n1} FPS goal for this {1}.":
        "Kare hızı yaklaşık {n0} FPS'e düşüyor ({0}); bu {1} için {n1} FPS hedefinin hemen altında.",
    "Frame rate dips to about {n0} FPS ({0}); the goal is {n1}. Settings ask more than this PC can hold.":
        "Kare hızı yaklaşık {n0} FPS'e düşüyor ({0}); hedef {n1}. Ayarlar bu bilgisayarın kaldırabileceğinden fazlasını istiyor.",
    "Holds about {n0} FPS in the worst moments ({0}) against a {n1} FPS goal.":
        "En kötü anlarda yaklaşık {n0} FPS'i koruyor ({0}); hedef {n1} FPS.",
    "About {n0}% performance is going unused while image quality sits at {n1}% of maximum. DCS could look better at no cost you would feel.":
        "Görüntü kalitesi en yüksek değerin %{n1} düzeyinde dururken performansın yaklaşık %{n0} kadarı kullanılmıyor. DCS, hissedeceğiniz bir bedel olmadan daha iyi görünebilir.",
    "Video memory is nearly full ({n0} of {n1} GB, {0}); this causes stutter when new scenery loads.":
        "Ekran belleği neredeyse dolu ({n0} / {n1} GB, {0}); bu, yeni arazi yüklenirken takılmaya yol açar.",
    "DCS draws a {n0}x{n1} picture across more than one screen (monitor setup \"{0}\"). That is counted in the frame-rate estimate; your resolution and monitor setup are kept exactly as they are.":
        "DCS, birden fazla ekrana yayılan {n0}x{n1} boyutunda bir görüntü çiziyor (monitör düzeni \"{0}\"). Bu, kare hızı tahminine dahil edilir; çözünürlüğünüz ve monitör düzeniniz olduğu gibi korunur.",
    "DCS draws a {n0}x{n1} picture across more than one screen. That is counted in the frame-rate estimate; your resolution and monitor setup are kept exactly as they are.":
        "DCS, birden fazla ekrana yayılan {n0}x{n1} boyutunda bir görüntü çiziyor. Bu, kare hızı tahminine dahil edilir; çözünürlüğünüz ve monitör düzeniniz olduğu gibi korunur.",
    "DCS is set to {n0}x{n1} but the desktop is {n2}x{n3}. The extra pixels are rendered and then thrown away or pushed off-screen.":
        "DCS {n0}x{n1} olarak ayarlı ama masaüstü {n2}x{n3}. Fazladan pikseller çizilir, sonra ya atılır ya da ekranın dışına taşar.",
    "Textures are not on High although the card has {n0} GB of video memory to hold them.":
        "Kartta onları tutacak {n0} GB ekran belleği olduğu hâlde dokular (Textures) Yüksek'te değil.",
    "Terrain textures are on Low; a {n0} GB card shows the High set with no frame-rate cost.":
        "Arazi dokuları (Terrain textures) Düşük'te; {n0} GB'lık bir kart Yüksek seti kare hızı kaybı olmadan gösterir.",
    "High textures on a {n0} GB card overflow video memory in most modules.":
        "{n0} GB'lık bir kartta Yüksek dokular çoğu modülde ekran belleğini taşırır.",
    "Preload radius is {n0} with {n1} GB of memory; this can push Windows into swapping.":
        "Ön yükleme yarıçapı (Preload radius) {n1} GB bellekle {n0}; bu, Windows'u disk belleğini (takas) kullanmaya itebilir.",
    "Preload radius is low for a PC with this much memory; raising it reduces pop-in stutter.":
        "Ön yükleme yarıçapı (Preload radius) bu kadar belleği olan bir bilgisayar için düşük; yükseltmek, nesneler belirirken oluşan takılmayı azaltır.",
    "DLSS Performance at this resolution makes cockpit text and distant aircraft blurry.":
        "Bu çözünürlükte DLSS Performance, kokpit yazılarını ve uzaktaki uçakları bulanıklaştırır.",
    "Upscaling is on although the PC has room to render at full resolution, which is sharper.":
        "Bilgisayarın tam çözünürlükte çizmeye gücü yettiği hâlde yükseltme (upscaling) açık; tam çözünürlük daha nettir.",
    "MSAA 4x is the most expensive anti-aliasing mode in DCS for this class of card.":
        "MSAA 4x, bu sınıftaki bir kart için DCS'teki en pahalı kenar yumuşatma modudur.",
    "Anti-aliasing is off; edges and distant aircraft shimmer.":
        "Kenar yumuşatma (anti-aliasing) kapalı; kenarlar ve uzaktaki uçaklar titreşir.",
    "Anisotropic filtering is low; 16x sharpens runways and ground textures almost for free.":
        "Anizotropik filtreleme düşük; 16x, pistleri ve zemin dokularını neredeyse bedelsiz netleştirir.",
    "{0} cost a lot on this graphics card for a small visual gain.":
        "{0}, bu ekran kartında küçük bir görsel kazanç için çok şeye mal oluyor.",
    "DCS is installed on a hard disk; an SSD removes most loading stutter.":
        "DCS bir sabit diske (HDD) kurulu; SSD, yükleme kaynaklı takılmaların çoğunu ortadan kaldırır.",

    # ---- VR advice (vr.py, data/vr.json) ------------------------------------------------------
    "your headset software": "VR gözlüğünüzün yazılımı",
    "VR is on, but this headset is not in our table yet (runtime: {0}). The estimate assumes a typical headset.":
        "VR açık, ama bu VR gözlüğü henüz tablomuzda yok (çalışma ortamı: {0}). Tahmin, tipik bir VR gözlüğü varsayıyor.",
    "VR is on, but this headset is not in our table yet. The estimate assumes a typical headset.":
        "VR açık, ama bu VR gözlüğü henüz tablomuzda yok. Tahmin, tipik bir VR gözlüğü varsayıyor.",
    "VR pixel density is {n0}. On a {0} 1.0 is already sharper than the lenses can show; the extra pixels only cost frame rate.":
        "VR piksel yoğunluğu (pixel density) {n0}. {0} üzerinde 1.0 zaten merceklerin gösterebildiğinden daha net; fazladan pikseller yalnızca kare hızından götürür.",
    "Both DCS pixel density and {0} render quality are above 1.0. They multiply; raise only one of them.":
        "Hem DCS piksel yoğunluğu hem de {0} tarafındaki render kalitesi 1.0'ın üzerinde. Bunlar birbiriyle çarpılır; yalnızca birini yükseltin.",
    "Bloom is on together with quad views; it shows visible seams around the sharp area.":
        "Bloom, quad views ile birlikte açık; net alanın çevresinde gözle görülür ek yerleri oluşturur.",
    "Lens effects are on together with quad views; they show visible seams around the sharp area.":
        "Mercek efektleri (Lens effects), quad views ile birlikte açık; net alanın çevresinde gözle görülür ek yerleri oluştururlar.",
    "Quad views is on, but on this PC the processor is the limit, not the graphics card. Quad views adds processor work and can lower the frame rate here.":
        "Quad views açık, ama bu bilgisayarda sınırlayan ekran kartı değil, işlemci. Quad views işlemciye ek yük bindirir ve burada kare hızını düşürebilir.",
    "Quad views (foveated rendering) is off. It is the biggest single frame-rate gain in VR when the graphics card is the limit: {0}.":
        "Quad views (foveated rendering) kapalı. Sınırlayan ekran kartı olduğunda VR'da tek başına en büyük kare hızı kazancını bu sağlar: {0}.",
    "tick Pimax OpenXR Quadviews in Pimax Play, then Use Quad Views in DCS's VR options":
        "Pimax Play'de Pimax OpenXR Quadviews'u, sonra DCS'in VR seçeneklerinde Use Quad Views'u işaretleyin",
    "it needs quad-views support in your headset software or the Quad-Views-Foveated add-on, then Use Quad Views in DCS's VR options":
        "VR gözlüğünüzün yazılımında quad-views desteği ya da Quad-Views-Foveated eklentisi gerekir; ardından DCS'in VR seçeneklerinde Use Quad Views'u işaretleyin",
    "Motion blur is on; in a headset it smears the picture and can cause discomfort.":
        "Hareket bulanıklığı (Motion blur) açık; VR gözlüğünde görüntüyü bulandırır ve rahatsızlık verebilir.",
    "Depth of field is on; in a headset it blurs whatever you are not expected to look at.":
        "Alan derinliği (Depth of field) açık; VR gözlüğünde bakmanız beklenmeyen her şeyi bulanıklaştırır.",
    "MSAA 4x in VR is very expensive at headset resolutions.": "VR'da MSAA 4x, gözlük çözünürlüklerinde çok pahalıdır.",
    "If DCS settings alone cannot hold the goal, lower render quality in {0} (now {n0}) before lowering DCS pixel density.":
        "DCS ayarları tek başına hedefi tutturamıyorsa, DCS piksel yoğunluğunu düşürmeden önce {0} içindeki render kalitesini (şu an {n0}) düşürün.",
    "If DCS settings alone cannot hold the goal, lower render quality in {0} before lowering DCS pixel density.":
        "DCS ayarları tek başına hedefi tutturamıyorsa, DCS piksel yoğunluğunu düşürmeden önce {0} içindeki render kalitesini düşürün.",
    "The goal assumes the headset runs at {n0} Hz. It can also run at {0} Hz ({1}); set DCS's frame-rate limit to match.":
        "Hedef, VR gözlüğünün {n0} Hz'de çalıştığını varsayar. Gözlük {0} Hz'de de çalışabilir ({1}); DCS'in kare hızı sınırını buna göre ayarlayın.",
    "VR pixel density": "VR piksel yoğunluğu (Pixel density)",
    "VR bloom effect": "VR bloom efekti",
    "Lens effects": "Mercek efektleri (Lens effects)",
    "Motion blur": "Hareket bulanıklığı (Motion blur)",
    "Depth of field": "Alan derinliği (Depth of field)",
    "None": "Yok",
    "Dirt": "Kir",
    "Flare": "Parlama",
    "Dirt and flare": "Kir ve parlama",
    "Simple": "Basit",
    "This headset is sharp enough at 1.0; a higher value renders pixels the lenses cannot show":
        "Bu VR gözlüğü 1.0'da yeterince net; daha yüksek bir değer, merceklerin gösteremeyeceği pikseller çizer",
    "Bloom shows visible seams when quad views (foveated rendering) is on":
        "Quad views (foveated rendering) açıkken bloom gözle görülür ek yerleri oluşturur",
    "Lens effects show visible seams when quad views (foveated rendering) is on":
        "Quad views (foveated rendering) açıkken mercek efektleri gözle görülür ek yerleri oluşturur",
    "Made for monitors; in a headset it smears the picture and can cause discomfort":
        "Monitörler için yapılmıştır; VR gözlüğünde görüntüyü bulandırır ve rahatsızlık verebilir",
    "Made for monitors; in a headset it blurs whatever you are not expected to look at":
        "Monitörler için yapılmıştır; VR gözlüğünde bakmanız beklenmeyen her şeyi bulanıklaştırır",

    # ---- settings table (data/settings.json, model.py) ----------------------------------------
    "Textures": "Dokular (Textures)",
    "Terrain textures": "Arazi dokuları (Terrain textures)",
    "Shadows": "Gölgeler (Shadows)",
    "Terrain object shadows": "Arazi nesnesi gölgeleri (Terrain object shadows)",
    "Clouds": "Bulutlar (Clouds)",
    "Visibility range": "Görüş mesafesi (Visib range)",
    "Water": "Su (Water)",
    "Volumetric lights": "Hacimsel ışıklar (Volumetric lights)",
    "Ambient occlusion (SSAO)": "Ortam gölgelemesi (SSAO)",
    "Screen-space reflections (SSLR)": "Ekran uzayı yansımaları (SSLR)",
    "Screen-space shadows (SSS)": "Ekran uzayı gölgeleri (SSS)",
    "Cockpit global illumination": "Kokpit küresel aydınlatması (Cockpit global illumination)",
    "Anisotropic filtering": "Anizotropik filtreleme (Anisotropic filtering)",
    "Forest distance": "Orman mesafesi (Forest visibility)",
    "Grass / clutter distance": "Çim / ayrıntı mesafesi (Clutter/grass)",
    "Civilian traffic": "Sivil trafik (Civ. traffic)",
    "Heat blur": "Isı bulanıklığı (Heat blur)",
    "Upscaling and anti-aliasing": "Yükseltme (upscaling) ve kenar yumuşatma",
    "Sharper aircraft, cockpits and vehicles": "Daha net uçaklar, kokpitler ve araçlar",
    "Sharper ground, runways and fields": "Daha net zemin, pistler ve tarlalar",
    "Crisper, more detailed shadows in the cockpit and on aircraft": "Kokpitte ve uçaklarda daha keskin, daha ayrıntılı gölgeler",
    "Buildings and trees cast proper shadows on the ground": "Binalar ve ağaçlar yere gerçek gölge düşürür",
    "Smoother, more detailed clouds": "Daha pürüzsüz, daha ayrıntılı bulutlar",
    "Buildings, trees and objects stay visible further away": "Binalar, ağaçlar ve nesneler daha uzaktan görünür kalır",
    "More realistic waves and reflections on the sea": "Denizde daha gerçekçi dalgalar ve yansımalar",
    "Visible light beams from lamps and landing lights": "Lambalardan ve iniş farlarından görünür ışık hüzmeleri",
    "Soft contact shadows in corners and under objects": "Köşelerde ve nesnelerin altında yumuşak temas gölgeleri",
    "Reflections on wet runways, water and glass": "Islak pistlerde, suda ve camda yansımalar",
    "Fine extra shadows on small details": "Küçük ayrıntılarda ince ek gölgeler",
    "More natural light bouncing around the cockpit": "Kokpitin içinde daha doğal yansıyan ışık",
    "Sharper runways and ground at shallow angles": "Sığ açılarda daha net pistler ve zemin",
    "Forests stay visible further away": "Ormanlar daha uzaktan görünür kalır",
    "Grass and small ground detail reach further out": "Çim ve küçük zemin ayrıntıları daha uzağa uzanır",
    "More cars and trains on roads and railways": "Yollarda ve demiryollarında daha fazla araba ve tren",
    "Heat shimmer behind jet engines": "Jet motorlarının arkasında ısı titreşimi",
    "Sharper picture: more of each frame is really drawn": "Daha net görüntü: her karenin daha büyük kısmı gerçekten çizilir",
    "Draws fewer pixels per frame to free up frame rate": "Kare hızını artırmak için kare başına daha az piksel çizer",
    "Lowered to free up frame rate": "Kare hızını artırmak için düşürüldü",
    "Low": "Düşük",
    "Medium": "Orta",
    "High": "Yüksek",
    "Ultra": "Ultra",
    "Extreme": "Aşırı (Extreme)",
    "Flat": "Düz (Flat)",
    "Flat only": "Yalnızca düz (Flat only)",
    "Default": "Varsayılan (Default)",
    "Standard": "Standart",
    "On": "Açık",
    "Off": "Kapalı",
    "No anti-aliasing": "Kenar yumuşatma yok",
    "{0} (native)": "{0} (tam çözünürlük)",
    "Smoothness": "Akıcılık",
    "Balanced": "Dengeli",
    "Quality": "Kalite",
    "{0} = {1}": "{0} = {1}",

    # ---- progress log (optimize.py, bench.py) -------------------------------------------------
    "Measuring your current settings...": "Şu anki ayarlarınız ölçülüyor...",
    "Holding {n0} FPS would cost too much image quality for the {0} choice on this PC; aiming for {n1}.":
        "Bu bilgisayarda {n0} FPS'i korumak, {0} seçimi için görüntü kalitesinden çok fazla götürür; hedef {n1} olarak alınıyor.",
    "Testing candidate {n0} ({0})...": "{n0}. aday test ediliyor ({0})...",
    "{0}: measurements do not make sense (lower was slower); using the estimate":
        "{0}: ölçümler tutarsız (düşük ayar daha yavaş çıktı); tahmin kullanılıyor",
    "Measuring {n0} settings changes in one DCS run: {0}...": "Tek DCS çalıştırmasında {n0} ayar değişikliği ölçülüyor: {0}...",
    "this run failed ({0}); using built-in estimates for these settings":
        "bu çalıştırma başarısız oldu ({0}); bu ayarlar için yerleşik tahminler kullanılıyor",
    "The PC's speed changed during this run (another program was probably using it). Discarding it and using built-in estimates for these settings.":
        "Bu çalıştırma sırasında bilgisayarın hızı değişti (büyük olasılıkla başka bir program kullanıyordu). Ölçüm atılıyor ve bu ayarlar için yerleşik tahminler kullanılıyor.",
    "Measuring your current settings (short run)...": "Şu anki ayarlarınız ölçülüyor (kısa çalıştırma)...",
    "Re-checking your current settings...": "Şu anki ayarlarınız yeniden kontrol ediliyor...",
    "re-check failed ({0}); discarding the last measurements": "yeniden kontrol başarısız oldu ({0}); son ölçümler atılıyor",
    "The PC's speed changed during these measurements (another program was probably using it). Discarding them and using built-in estimates for: {0}":
        "Bu ölçümler sırasında bilgisayarın hızı değişti (büyük olasılıkla başka bir program kullanıyordu). Ölçümler atılıyor ve şunlar için yerleşik tahminler kullanılıyor: {0}",
    "Measuring {0} = {1}...": "Ölçülüyor: {0} = {1}...",
    "skipped ({0}); using the built-in estimate for this level": "atlandı ({0}); bu seviye için yerleşik tahmin kullanılıyor",
    "only {n0} frames recorded": "yalnızca {n0} kare kaydedildi",
    "benchmark did not finish: {0}": "test tamamlanmadı: {0}",
    "Could not find a free network port on this PC for the test.": "Test için bu bilgisayarda boş bir ağ bağlantı noktası bulunamadı.",
    "DCS is running. Close it first; DCS Graphics Optimizer never touches a running game.":
        "DCS çalışıyor. Önce kapatın; DCS Graphics Optimizer çalışan bir oyuna asla dokunmaz.",
    "Another program is using your graphics card ({n0}% busy before DCS has even started). Close games, video renders, AI tools and browser videos, then try again; otherwise the results would be wrong.":
        "Başka bir program ekran kartınızı kullanıyor (DCS daha başlamadan %{n0} meşgul). Oyunları, video işlemeyi, yapay zekâ araçlarını ve tarayıcıdaki videoları kapatıp yeniden deneyin; yoksa sonuçlar yanlış çıkar.",
    "WARNING: graphics card is {n0}% busy before DCS starts; results will be unreliable.":
        "UYARI: ekran kartı DCS başlamadan önce %{n0} meşgul; sonuçlar güvenilir olmayacak.",
    "The graphics card is {n0}% busy before DCS starts, most likely the headset software's home screen. That's expected in VR; DCS takes over the headset when it starts.":
        "Ekran kartı DCS başlamadan önce %{n0} meşgul; büyük olasılıkla VR gözlüğü yazılımının ana ekranı yüzünden. VR'da bu beklenen bir durumdur; DCS başladığında gözlüğü devralır.",
    "WARNING: other programs are using {n0} GB of {n1} GB of video memory before DCS starts. The test continues, but the video memory figures will include them and the recommendation may be more cautious than needed. Close them and test again for the best result.":
        "UYARI: DCS başlamadan önce diğer programlar {n1} GB ekran belleğinin {n0} GB'ını kullanıyor. Test devam ediyor, ama ekran belleği rakamları onları da içerecek ve öneri gereğinden temkinli olabilir. En iyi sonuç için onları kapatıp yeniden test edin.",
    "WARNING: other programs are using {n0} GB of video memory before DCS starts. The test continues, but the video memory figures will include them and the recommendation may be more cautious than needed. Close them and test again for the best result.":
        "UYARI: DCS başlamadan önce diğer programlar {n0} GB ekran belleği kullanıyor. Test devam ediyor, ama ekran belleği rakamları onları da içerecek ve öneri gereğinden temkinli olabilir. En iyi sonuç için onları kapatıp yeniden test edin.",
    "The benchmark script inside this program is damaged.": "Bu programın içindeki test betiği bozulmuş.",
    "{0}: avg {n0} FPS, 1% low {n1} FPS, VRAM {n2} MB, {n3}s": "{0}: ort. {n0} FPS, %1 düşük {n1} FPS, VRAM {n2} MB, {n3} sn",
    "{n0} trials in {n1}s, VRAM peak {n2} MB": "{n1} sn içinde {n0} deneme, en yüksek VRAM {n2} MB",
    "DCS was started again by another program (for example Steam); following that one...":
        "DCS başka bir program tarafından (örneğin Steam) yeniden başlatıldı; o izleniyor...",
    "The benchmark finished but DCS did not close by itself; closing it.": "Test bitti ama DCS kendiliğinden kapanmadı; kapatılıyor.",
    "DCS did not finish the benchmark in time. Close DCS, then try again.": "DCS testi zamanında bitirmedi. DCS'i kapatıp yeniden deneyin.",
    "DCS is taking longer than usual but is still working (an add-on may be doing one-time setup); waiting a bit more...":
        "DCS normalden uzun sürüyor ama hâlâ çalışıyor (bir eklenti tek seferlik kurulum yapıyor olabilir); biraz daha bekleniyor...",
    "Windows started this program with a setting from your web browser that makes DCS load the wrong files, so DCS would stop with an \"entry point not found\" error. Close the optimizer and start DCSGraphicsOptimizer.exe by double-clicking it in File Explorer, not from the browser's download list.":
        "Windows bu programı, web tarayıcınızdan gelen ve DCS'in yanlış dosyaları yüklemesine yol açan bir ayarla başlattı; bu yüzden DCS \"entry point not found\" hatasıyla dururdu. Optimizer'ı kapatın ve DCSGraphicsOptimizer.exe'yi tarayıcının indirilenler listesinden değil, Dosya Gezgini'nde çift tıklayarak başlatın.",
    "This is the Steam edition of DCS, and Steam is not open. Open Steam and sign in (tick \"Remember me\"), then try again.":
        "Bu, DCS'in Steam sürümü ve Steam açık değil. Steam'i açıp oturum açın (\"Beni hatırla\"yı işaretleyin), sonra yeniden deneyin.",
    "DCS closed straight away; waiting a moment and starting it again...": "DCS hemen kapandı; biraz beklenip yeniden başlatılıyor...",
    "DCS did not finish the benchmark in time and was closed. Check that DCS starts normally and is logged in.":
        "DCS testi zamanında bitirmedi ve kapatıldı. DCS'in normal şekilde başladığını ve oturumun açık olduğunu kontrol edin.",
    "Steam is starting DCS. If Steam asks about launch options, click Continue (the test needs them); the test waits for you.":
        "DCS'i Steam başlatıyor. Steam başlatma seçeneklerini sorarsa Devam'a (Continue) tıklayın (test bunlara ihtiyaç duyar); test sizi bekler.",
    "DCS closed straight away twice when this tool started it, so the test was stopped. Start DCS once yourself and check it reaches the main menu without asking anything (log-in, update, or a message to click), close it, then try again. If you start DCS through Steam, start it once from Steam first.":
        "Bu araç başlattığında DCS iki kez hemen kapandı, bu yüzden test durduruldu. DCS'i bir kez kendiniz başlatın ve hiçbir şey sormadan (oturum açma, güncelleme ya da tıklanacak bir mesaj) ana menüye ulaştığını kontrol edin, kapatın, sonra yeniden deneyin. DCS'i Steam üzerinden başlatıyorsanız önce bir kez Steam'den başlatın.",
    "DCS closed without writing a benchmark result (a copy of its log is in Config\\dcstune-last-failure.log).":
        "DCS bir test sonucu yazmadan kapandı (kaydının bir kopyası Config\\dcstune-last-failure.log dosyasında).",
    "DCS could not show its picture in the headset, so it ran on the monitor instead. Nothing was measured. Check that the headset is connected, switched on and working in its own software, then try again.":
        "DCS görüntüsünü VR gözlüğünde gösteremedi, bu yüzden monitörde çalıştı. Hiçbir şey ölçülmedi. Gözlüğün bağlı, açık ve kendi yazılımında çalışır durumda olduğunu kontrol edip yeniden deneyin.",

    # ---- report (report.py) -------------------------------------------------------------------
    "Thorough test": "Kapsamlı test",
    "Test and optimize": "Test et ve optimize et",
    "City pass": "Şehir üzerinden geçiş",
    "Airfield ramp": "Havaalanı apronu",
    "Cloud layer": "Bulut katmanı",
    "not measured": "ölçülmedi",
    "Almost nothing ({0})": "Neredeyse hiç ({0})",
    "About {n0}% of frame rate ({0})": "Kare hızından yaklaşık %{n0} ({0})",
    "About {n0}% frame rate gained ({0})": "Yaklaşık %{n0} kare hızı kazancı ({0})",
    "{n0} minutes": "{n0} dakika",
    "DCS started {n0} times": "DCS {n0} kez başlatıldı",
    "Overall": "Genel",
    "Grade": "Not",
    "Your settings are already the best match.": "Ayarlarınız zaten en uygun durumda.",
    "Goal: hold {n0} FPS in the worst moments ({0}).": "Hedef: en kötü anlarda {n0} FPS'i korumak ({0}).",
    "Goal: hold {n0} FPS in the worst moments.": "Hedef: en kötü anlarda {n0} FPS'i korumak.",
    "These settings were applied on {0}. Use Undo in the app to go back.":
        "Bu ayarlar {0} tarihinde uygulandı. Geri dönmek için uygulamada Geri al'ı kullanın.",
    "VR is switched on in this DCS profile. This test ran on the monitor, so the numbers below are monitor numbers, and no VR setting is changed. DCS uses the same graphics settings in the headset, so applying these can make VR slower; the tool asks before it does.":
        "Bu DCS profilinde VR açık. Bu test monitörde çalıştı; bu yüzden aşağıdaki sayılar monitör sayılarıdır ve hiçbir VR ayarı değiştirilmez. DCS, VR gözlüğünde de aynı grafik ayarlarını kullanır; bunları uygulamak VR'ı yavaşlatabilir. Araç uygulamadan önce sorar.",
    "Measured in the VR headset.": "VR gözlüğünde ölçüldü.",
    "Another program was using the PC during part of this test, so some measurements were discarded. For the most accurate result, close other programs and run it again.":
        "Bu testin bir bölümünde başka bir program bilgisayarı kullanıyordu, bu yüzden bazı ölçümler atıldı. En doğru sonuç için diğer programları kapatıp testi yeniden çalıştırın.",
    "Other programs were using {n0} GB of video memory before DCS started. The video memory figures below include them, and the recommendation may be more cautious than needed. For the most accurate result, close them and run the test again.":
        "DCS başlamadan önce diğer programlar {n0} GB ekran belleği kullanıyordu. Aşağıdaki ekran belleği rakamları onları da içerir ve öneri gereğinden temkinli olabilir. En doğru sonuç için onları kapatıp testi yeniden çalıştırın.",
    "This PC cannot hold {n0} FPS in the heaviest scene; this is the smoothest result measured.":
        "Bu bilgisayar en ağır sahnede {n0} FPS'i koruyamıyor; bu, ölçülen en akıcı sonuçtur.",
    "Before": "Önce",
    "Your settings": "Ayarlarınız",
    "Recommended": "Önerilen",
    "Settings grade": "Ayar notu",
    "Overall score": "Genel puan",
    "Worst moments (1% low)": "En kötü anlar (%1 düşük)",
    "Average frame rate": "Ortalama kare hızı",
    "Video memory at peak": "En yüksek ekran belleği kullanımı",
    "Image quality": "Görüntü kalitesi",
    "{n0}% of maximum": "en yüksek değerin %{n0} kadarı",
    "Measured in DCS": "DCS'te ölçüldü",
    "What changes, and what it costs on this PC": "Neler değişiyor ve bu bilgisayarda neye mal oluyor",
    "Setting": "Ayar",
    "Now": "Şimdi",
    "What you get": "Ne kazanırsınız",
    "Cost on this PC": "Bu bilgisayardaki bedeli",
    "Still worth knowing": "Yine de bilmeye değer",
    "This tool does not change this, so it is still true: ": "Bu araç bunu değiştirmez, dolayısıyla hâlâ geçerli: ",
    "What each setting costs on this PC (measured)": "Her ayarın bu bilgisayardaki bedeli (ölçüldü)",
    "Compared": "Karşılaştırma",
    "Frame rate it costs": "Götürdüğü kare hızı",
    "Almost nothing": "Neredeyse hiç",
    "About {n0}%": "Yaklaşık %{n0}",
    "{0} instead of {1}": "{1} yerine {0}",
    "The same moment, before and recommended": "Aynı an: önce ve önerilen",
    "Screenshots from the test": "Testten ekran görüntüleri",
    "This PC for DCS:": "DCS için bu bilgisayar:",
    "DCS Graphics Optimizer report": "DCS Graphics Optimizer raporu",
    "DCS Graphics Optimizer &ndash; test report": "DCS Graphics Optimizer &ndash; test raporu",
    "Frame rates were measured on this PC in three fixed scenes on the Caucasus map (a city pass, an airfield ramp and a cloud layer). Other maps, missions and multiplayer servers will run differently. Made by DCS Graphics Optimizer; nothing in this report was sent anywhere.":
        "Kare hızları bu bilgisayarda, Kafkasya haritasındaki üç sabit sahnede (şehir üzerinden geçiş, havaalanı apronu ve bulut katmanı) ölçüldü. Diğer haritalar, görevler ve çok oyunculu sunucular farklı çalışır. DCS Graphics Optimizer tarafından oluşturuldu; bu rapordaki hiçbir şey hiçbir yere gönderilmedi.",
}
