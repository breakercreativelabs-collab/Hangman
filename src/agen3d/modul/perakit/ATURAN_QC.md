# Buku Aturan & QC: Perakit (model dari prompt teks)

Perakit membangun model dari **rancangan bentuk** (`proyek/<id>/rancangan.toml`) yang ditulis Claude dari prompt teks: Claude = otak (nalar, ukuran, rancangan, penilaian), perakit = tangan (SDF -> mesh deterministik, QC angka). Non-generatif. **Sebelum menulis rancangan, Claude wajib riset web contoh terbaik** (gambar referensi, dimensi nyata, ciri kualitas) dan mengutip sumbernya di `[objek] sumber` (keputusan pengguna 2026-10-16). Cacat yang ditemukan mata **wajib** dicatat di sini lalu diwujudkan di kode/rancangan.

Format: ID · cacat/risiko · ditemukan oleh · perbaikan · cek angka (QC) · ambang lulus · status

| ID | Cacat / risiko | Ditemukan | Perbaikan | Cek angka (QC) | Ambang lulus | Status |
|---|---|---|---|---|---|---|
| KC-01 | Tinggi tidak sesuai rancangan | Pencegahan | n/a | tinggi bbox Z (mm) | rancangan ± `toleransi_tinggi_mm` | ✅ v1 61,88 / 62 ± 0,5 |
| KC-02 | Diameter alas tidak sesuai rancangan | Pencegahan | n/a | 2 × radius maks titik z < 3 mm | rancangan ± `toleransi_diameter_mm` | ✅ v1 35,00 / 35 ± 0,4 |
| KC-03 | Mesh bocor (tidak bisa dicetak 3D / boolean) | Pencegahan | SDF -> quad openvdb (tertutup) | tepi yang tidak dipakai tepat 2 muka | = 0 | ✅ v1 |
| KC-04 | Tidak simetris kiri-kanan | Ukur, v1 (decimate asimetris: jarak titik-ke-titik 0,91 mm; decimate simetri Blender merusak manifold) | Decimate biasa + ukur titik cermin ke **permukaan** (BVH), bukan ke titik | maks jarak titik cermin Y ke permukaan | ≤ `toleransi_simetri_mm` (0,3) | ✅ v1 0,05 mm |
| KC-05 | Bidak terguling (kepala terlalu maju) | Pencegahan | n/a | jarak horizontal titik berat volume ke sumbu | ≤ 0,5 × radius tapak | ✅ v1 0,29 / 8,4 mm |
| KC-06 | Poligon berlebihan | Pencegahan | Decimate ke `target_segitiga` | jumlah segitiga | ≤ `maks_poligon` | ✅ v1 120.000 |
| KC-07 | Kepala tampak depan seperti papan pipih | Mata, v1 (2026-10-16) | Rancangan rev 1: `bulat_mm` 3,0 -> 4,2, tebal rahang 7,4 -> 7,8, detail `pipi` | (visual, belum ada angka) | n/a | ✅ rev 1 |
| KC-07 | Semua bagian "empuk" (fillet 1-2 mm di mana-mana), tanpa variasi tepi keras/lunak seperti ukiran asli | Mata pengguna, rev 3 (2026-10-16) | Rev 4: `pahat_bidang` di kerangka lokal (6 bidang: punggung hidung, sisi moncong, depan hidung, dahi, pipi rahang, bawah rahang); otot/leher tetap lunak | per bidang: luas datar (muka <= 0,1 mm dari bidang, normal <= 8 deg) DAN sudut lipat tepi = P75 sudut normal muka di cincin 0,7 mm luar bidang | luas >= `min_luas_mm2` (2) DAN sudut >= `min_sudut_tepi` (20 deg; kalibrasi: rev 4 23-26 deg vs dihaluskan Laplacian 20x = 10-13 deg) | ✅ rev 4 min 23,3 deg |
| KC-08 | Surai berupa rusuk horizontal (terbaca "radiator"), bukan helai | Mata, rev 1 | rev 2: pita surai dipisah alur (`kurangi_garis`) + garis rapat; helai belum | (visual) | n/a | ⚠️ |
| KC-09 | Kepala lunak seperti bantal; kuda kayu asli berbidang pahat (tepi tegas pipi, dahi, batang hidung) | Mata pengguna, foto pembanding (2026-10-16) | Resep `pahat_bidang` (bidang datar SDF berwilayah, transisi halus) + 3 bidang (pipi, leher, sisi moncong) | (visual) | n/a | ✅ rev 2 |
| KC-10 | Alas rendah bertingkat; asli = alas tinggi menggembung (bola besar + kerah + leher ramping), ±35% tinggi | Mata pengguna, foto pembanding | Profil `putar` rev 2 (parameter saja): alas 23,5 mm, bola Ø36 | rasio tinggi alas / tinggi total | 0,30-0,38 (belum otomatis) | ✅ rev 2 = 0,38 |
| KC-11 | Moncong pendek dan tumpul; asli = moncong panjang kotak, mulut terbuka, dagu menonjol, leher depan cekung ramping | Mata pengguna, foto pembanding | Siluet rev 2 (parameter): moncong panjang, takik mulut terbuka, dagu, leher condong | (visual) | n/a | ✅ rev 2 |
| KC-12 | Telinga berupa satu blok terbelah; asli = dua telinga runcing terpisah dan cekung | Mata pengguna, foto pembanding | Resep `tambah_/kurangi_kerucut` (kerucut membulat dipipihkan) = telinga + cekungnya | (visual) | n/a | ✅ rev 2 |
| KC-13 | Bahan polos; asli = kayu berserat | Mata pengguna, foto pembanding | `bahan_kayu` (cincin Z berpusat di luar bidak + distorsi memanjang) via `[bahan]` | (visual) | n/a | ⏸ ditunda: keputusan pengguna fokus modeling dulu (render clay abu) |
| KC-14 | Bidang pahat leher ikut memotong kerah alas (tampak depan bertakik) | Mata, rev 2 | Wilayah pahat dinaikkan ke z ≥ 25,5 | (visual) | n/a | ✅ rev 2b |
| KC-15 | Kayu cokelat tampak peach (lampu terlalu terang) | Mata, rev 2 | Exposure -1 di studio lembar kontak | (visual) | n/a | ✅ rev 2b |
| KC-16 | Surai tetap rusuk mendatar (KC-08) walau sudah ada alur batas pita | Mata, rev 2 | Rencana: resep helai | (visual) | n/a | 🔜 |
| KC-17 | Wajah tidak terbaca kuda (rev 2: kepala = siluet ditebalkan + bidang pahat = "papan") | Mata pengguna (2026-10-16) | Rev 3: kepala & leher disusun primitif anatomis (elipsoid tengkorak/rahang/moncong, kerucut batang hidung/rahang bawah, tabung leher meruncing, krista surai) di `[[kerangka]]` lokal kepala (+ `skala`) | (visual: tampak "wajah" close-up di lembar kontak) | n/a | ✅ rev 3 |
| KC-18 | Alis menonjol ke samping seperti telinga (tampak depan) | Mata, rev 3 | alis r 1,9 -> 1,4, masuk 0,6 mm | (visual) | n/a | ✅ rev 3b |
| KC-19 | Celah mulut nyaris tak terlihat | Mata, rev 3b | Rencana: alur lebih dalam / takik siluet | (visual) | n/a | 🔜 |
| KC-20 | Bidang pahat memotong bagian lain di wilayahnya (pipi terlalu menunduk = takik "luka"; bawah rahang ikut memotong leher) | Mata, rev 4 | Normal pipi -0,35 -> -0,15; wilayah bawah rahang u 11-22; leher lebih lebar (skala y 0,84) + tenggorokan lunak | (visual) | n/a | ✅ rev 4b |
| KC-21 | Pertemuan rahang (jowl) dan rahang bawah = alur cekung gelap; di foto = punggung/tepi menonjol | Mata, rev 4b | Rencana: bidang pahat bertemu (dua bidang membentuk punggung) alih-alih elipsoid menggantung | (visual) | n/a | 🔜 |
| KC-22 | Area mata sampai pipi tidak rapi; pipi sangat cekung seperti lubang | Mata pengguna, rev 4 (2026-10-16) | Dugaan akar: kepala = banyak gumpalan terpisah (tengkorak, rahang, batang hidung) yang digabung -> lembah cekung di sambungan + rongga mata + alur pipi + bidang pipi menumpuk di area yang sama. Rencana: massa dasar kepala SATU bentuk menyatu dulu, baru dipahat | Rencana: deteksi cekung tak disengaja (kelengkungan negatif di area yang rancangannya cembung) | rencana | ✅ rev 5 (mata; angka 🔜): kepala = 1 massa baji + 2 tonjolan lunak, alis & alur pipi dibuang -> lubang hilang |
| KC-23 | Dagu / bawah mulut tidak rapi | Mata pengguna, rev 4 | Dugaan: alur mulut + elipsoid dagu + bidang bawah rahang bertumpuk. Rev 5: rahang bawah = bagian massa kepala, dagu 1 tonjolan, bidang bawah rahang dipindah ke belakang dagu (maks 2 operasi per area) | (visual) | n/a | ✅ rev 5 (mata) |
| KC-24 | Tepi bidang pipi rahang lunak (21 deg, nyaris ambang 20) karena bidang hampir menyinggung permukaan pipi yang landai | Ukur, rev 5 | Pahat 0,3 mm lebih dalam (20 -> 21 deg); dugaan: butuh normal lebih miring bila pipi harus tegas | KC-07 | >= 20 deg | ⚠️ rev 5b lulus tipis |
| KC-25 | Pose/proporsi beda dari referensi: kepala terlalu menunduk & panjang (moncong z 34 vs referensi ~41), leher terlihat pendek | Juri banding (render sudut sama vs referensi), rev 6 | Kerangka kepala sudut 32 -> 22, skala 1,12 -> 0,95, asal z 57 -> 55,5 (dari tinggi mata/moncong referensi; sumbu Z tidak terdistorsi sudut 3/4) | (visual banding; rencana: tinggi titik kunci vs referensi) | n/a | ✅ rev 6b |
| KC-26 | Telinga duri tipis (referensi: daun lebar tebal); mulut garis pendek (referensi: celah terbuka panjang); surai gerigi roda gigi (referensi: garis halus rapat); bola mata menonjol | Juri banding, rev 6 | Telinga r1 3,3 r2 1,0 tebal 0,8; mulut alur 7 titik r 0,7 membuka di depan; krista r 1,9 + takik r 0,5 jarak 1,6; bola mata r 0,85 | (visual) | n/a | ✅ rev 6 |
| KC-27 | Rongga antara rahang dan leher + dada menggembung terbaca "kait"; depan leher tegak seperti tiang | Juri banding + tampak samping; diagnosis 2 varian paralel (bidang leher diperpanjang / dimatikan -> bukan penyebab) | Tabung "leher depan" yang tepinya mengikuti garis referensi (x5,z42)->(x11,z24) + bidang "depan leher" | KC-07 (depan leher 32 deg) | >= 20 deg | ✅ rev 6e |
| KC-28 | Semua tepi keras setajam silet (punggung hidung 69 deg); tepi ukiran asli sedikit membulat | Juri banding, rev 6e | Rencana: bevel tepi bidang pahat (pahat dengan jari-jari tepi) | rencana: sudut maks | rencana | 🔜 |
| KC-29 | Kuda rev 6 dinilai pengguna "kemunduran, hancur" walau QC angka lulus dan tiap putaran banding terasa memperbaiki | Pengguna (2026-10-16) | Kuda DIPARKIR (rev 5 = versi terbaik menurut pengguna; rev 6 tetap di repo sebagai catatan). Pindah ke tangga kesulitan: bidak bubut dulu (pion) | (penilaian pengguna) | n/a | ⏸ diparkir |
| KC-30 | Revolusi profil ruas lurus -> pita cincin terlihat di bola/badan (pion rev 0) | Mata, pion rev 0 | `profil_halus` (Catmull-Rom sentripetal) + `profil_tajam` (indeks sudut pemotong kurva; tanpa ini kurva melengkung keluar 0,3 mm: tinggi 53,29, alas 32,28) | KC-01/02 menangkap pergeseran | toleransi rancangan | ✅ pion rev 1b |
| KC-31 | Terlalu lambat: pion 98 s (medan SDF 55 s) padahal profesional < 1 menit | Pengguna (2026-10-16) | `putar` menghitung jarak 2D sekali di kisi (r, z) lalu bilinear (bukan per voxel 3D x 600 ruas) | waktu bangun tanpa render | pion: medan 3,0 s, total 12 s (CPU cloud); dengan 6 render 67 s; `--mode pratinjau` (1 render, tanpa negatif) 12,7 s wall; benteng prompt -> pratinjau 37 s | ✅ |
| KC-32 | Mahkota ratu "kulit telur pecah": lekuk bulat merobek dinding cawan tipis (1,8 mm) | Mata, ratu rev 0-1 | Dinding 3,6 mm + takik V (`kurangi_kerucut` x8 via `putar_n`), takik 2,4 mm di bawah tepi | (visual) | n/a | ✅ ratu rev 2b |
| KC-33 | Detail berulang (`putar_n`) dihitung di seluruh kisi -> medan ratu 35,7 s (pion 3 s) | Ukur, ratu | Rencana: hitung detail hanya di kotak batasnya | waktu medan | rencana < 10 s | 🔜 |
| KC-34 | Kuda v2 rev 0 dari nalar: moncong z 37 (referensi ~45), alas bertumpuk seperti per, kepala-leher lebar & datar dari depan, pipi menggembung, telinga runcing, "wajah babi" | Juri banding 3D (referensi 3D riset, 6 sudut sama) | rev 1: proporsi diukur dari referensi 3D (tinggi moncong, lengkung punggung, tenggorokan, alas rendah 1 gelang, setengah tebal 6-8 mm); rev 2: penampang oval (bulat 7), `tebal_x` punggung menyempit, lubang hidung ke sisi | (visual banding 3D) | n/a | ✅ rev 2 (menunggu pengguna) |
| KC-35 | Detail wajah tak terlihat (mata/hidung/mulut): posisi Y ditebak, setelah penampang dibuat oval permukaan bergeser -> bola ukir melayang di luar kepala | Pengguna + hitung, kuda v2 rev 2 | `kedalaman`/`tonjol`: perakit mencari permukaan Y sendiri lalu menempel/mengukir; galat keras bila detail tidak menyentuh benda (menangkap titik mulut di dalam celah) | galat keras bila kolom kosong | - | ✅ rev 3 |

## Juri kualitas ASET (jalur aset, keputusan pengguna 2026-10-17; `aset.py`)
Aset terbuka berlisensi dinilai SEBELUM dipakai. Skor 0-100 berbobot; A >= 85, B >= 65 (keduanya wajib KA-01 lulus), selain itu C. Mata Claude tetap menilai render sesudahnya (angka tidak menangkap keindahan).

| ID | Cek | Ambang | Bobot | Kenapa |
|---|---|---|---|---|
| KA-01 | Lisensi terbuka + atribusi tertulis | CC0 / CC-BY / MIT + atribusi | 30 | tanpa ini aset tidak boleh dipakai sama sekali |
| KA-02 | Tepi bocor (non-manifold), setelah las vertex | <= 0,1% | 15 | konversi SDF butuh mesh tertutup (ambang 1% bocor di uji negatif lubang 10%) |
| KA-03 | Orientasi normal (volume bertanda > 0) | > 0 | 10 | normal terbalik = dalam/luar tertukar |
| KA-04 | Segitiga serpih (rasio > 10) | <= 5% | 10 | mesh kotor/scan mentah; catatan: subdivisi 2 level menaikkan ke ~5,1% (lulus tipis gagal; dicatat, tidak dilonggarkan) |
| KA-05 | Jumlah segitiga | 2.000-500.000 | 10 | terlalu kasar / terlalu berat |
| KA-06 | Bagian lepas | <= 3 (atur per rancangan) | 10 | sampah, objek ganda |
| KA-07 | Simetri cermin Y (median) | <= 0,5 mm | 15 | bidak simetris; aset miring/rusak |
| KA-08 | Kelengkapan ciri wajib per `jenis_objek` (`CIRI_WAJIB`, mis. kuda: mata, telinga, lubang hidung, mulut, surai): ada di `ciri_aset` (diperiksa Claude di close-up) atau sebagai `[[detail]]` bernama ciri itu | tidak ada yang hilang | ikut menentukan LULUS model | cacat dari mata pengguna: aset kuda nilai A 90 tapi **tanpa mata**; KA-01..07 hanya mengukur kebersihan mesh, bukan anatomi. Uji negatif: detail mata dibuang -> gagal |

Pelajaran jalur aset: (1) glTF memecah vertex di sambungan UV -> tampak 7,6% bocor & 1.096 bagian lepas; WAJIB las vertex sebelum menilai/konversi. (2) Aset low-poly (11 rb segitiga) tampak berfaset setelah SDF -> `subdiv = 2` (Catmull-Clark setelah las). (3) Tanda potongan: buang z < potong_z = kurangi SDF (Z - potong_z); salah tanda membuang seluruh kepala (tertangkap KC-01). (4) Aset nilai A belum tentu lengkap: periksa ciri wajib di close-up, tambal yang hilang dengan `[[detail]]` relatif permukaan (KA-08). (5) Sambungan aset ke bagian buatan: bawah aset yang membulat tampak "kelereng di atas piring" (mata pengguna: "terpisah, tidak menyatu") -> `perpanjang_dari_z` (penampang diteruskan lurus ke bawah) + `gabung_halus_mm` 2,5.

## QC SET (perintah `perakit set`, `set.py`; 2026-10-17)
Bidak dinilai sebagai SATU set di papan posisi awal, bukan sendiri-sendiri. Ukuran diukur dari model jadi (glb), bukan dari angka rancangan.

| ID | Cek | Ambang | Kenapa / sumber |
|---|---|---|---|
| KS-01 | Urutan tinggi raja > ratu > gajah > kuda > benteng > pion | turun tegas | hierarki Staunton; pion setinggi 2x tertangkap |
| KS-02 | Alas raja / sisi petak | 0,68-0,80 | panduan 75-78% (USCF/chess.com; rentang sumber 68-85%) |
| KS-03 | Sisi petak | 50-60 mm | FIDE (turnamen) |
| KS-04 | Alas terbesar / sisi petak | <= 0,80 | ada celah antar bidak bertetangga |
| KS-05 | Posisi awal sah | 32 bidak, petak unik, jumlah per jenis, raja e / ratu d | raja-ratu tertukar & dua bidak satu petak tertangkap |
| KS-06 | Semua bidak lulus QC sendiri (laporan KC/KA) | semua | set tidak boleh menutupi bidak yang gagal |

Uji negatif set (7): pion 2x, petak 40 mm, petak 70 mm, alas kuda 50 mm, raja-ratu tertukar, dua bidak satu petak, kuda gagal QC sendiri.

## Mode tonton (perintah `perakit bangun --tonton 1`, `uji_tonton`; tonton.py + addon/agen3d; 2026-10-17)
| ID | Cek | Ambang | Kenapa |
|---|---|---|---|
| KT-01 | Langkah lengkap, terakhir = model.glb, manifest selesai | >= 2 langkah | penonton harus melihat sampai mesh serah |
| KT-02 | Mesh akhir di Blender terbuka identik dengan mesh serah headless | selisih < 1e-6 m | keputusan pengguna: tonton tidak boleh beda dengan hasil |
| KT-03 | Setiap langkah termuat (mesh tidak kosong) | semua | langkah hilang = proses terlihat melompat |
| KT-04 | Efek tumbuh berakhir di skala 1 | 1,0 | objek tidak boleh tertinggal gepeng |
| KT-05 | Pemuat tahan manifest/npz setengah tertulis | None, tanpa galat | **cacat nyata yang ditemukan uji ini**: npz terpotong -> BadZipFile menghentikan pemantau; ditangkap, dicoba tik berikutnya |
Uji negatif (4): langkah akhir hilang, akhir = langkah pertama, satu langkah gagal dimuat, tumbuh berhenti di tengah. Timer/viewport GUI wajib dicek di laptop (docs/TONTON.md).

## Uji negatif (wajib, jalan di setiap `perakit bangun`)
Mesh hasil dirusak 6 cara; tiap KC-01..06 wajib gagal pada perusaknya sendiri (tinggi × 1,05; alas × 1,04; 1 muka dibuang; geser Y 1 mm di atas z 30; kepala maju 25 mm; batas poligon 1000). v1: 6/6 tertangkap, masing-masing hanya cek miliknya. Jalur aset: + 7 uji negatif KA (lisensi kosong, 10% segitiga dibuang, normal dibalik, serpih ditambah, dipangkas 1.000, 5 salinan, separuh digeser) -> kuda aset 13/13. Sejak rev 4 (bila rancangan punya bidang ber-`min_luas_mm2`): + KC-07 wajib gagal pada mesh dihaluskan Laplacian 20x ("semua empuk"); 7/7. Catatan: Laplacian 3-6x tidak cukup (bidang datar tetap datar; metrik luas saja bocor -> ditambah sudut lipat tepi).

## Celah katalog (dicatat agar katalog tumbuh dari kebutuhan nyata)
- Helai/serat (surai, rambut): belum ada resep; didekati takik kapsul.
- Bidang pahat, telinga, serat kayu: ditambahkan rev 2 (dari foto pembanding pengguna, dipakai sebagai pengetahuan bentuk).
- Riset gambar web dari cloud: diblokir kebijakan jaringan environment (403 di wikimedia, houseofstaunton, jaqueslondon, chessbazaar, dll.); hanya cuplikan teks pencarian. Perlu domain diizinkan atau riset dilakukan di laptop.

## Pelajaran umum (berlaku untuk model apa pun, dari kuda catur rev 0-4, 2026-10-16)
1. **Riset dulu, baru rancang.** Nalar saja meleset (rev 0: alas, moncong, telinga salah). Gambar referensi + dimensi nyata + ciri kualitas, kutip di `[objek] sumber`.
2. **Pilih resep sesuai jenis bentuk.** Benda putar -> `putar`; benda pipih/siluet -> `bantal`; organik (hewan, wajah) -> susun primitif anatomis. Salah resep tidak bisa ditambal parameter (rev 2: wajah "papan").
3. **Besar dulu, detail belakangan** (massa utama -> bentuk sekunder -> detail). Detail di atas massa yang salah hanya menambah kekacauan.
4. **Massa dasar menyatu, baru dipahat.** Banyak gumpalan terpisah yang digabung halus menimbulkan lembah cekung tak sengaja di sambungan (KC-22). Terbukti rev 5: 6 gumpalan -> 1 baji + 2 tonjolan lunak, lubang pipi hilang.
5. **Variasi tepi diputuskan per area:** keras (bidang, tulang, tepi buatan) vs lunak (otot, kain). Semua lunak = boneka; semua keras = balok (KC-07).
6. **Operasi berwilayah bisa bocor** ke bagian lain (bidang rahang memotong leher, KC-20): wilayah sesempit mungkin, cek tampak dari semua sisi.
7. **Berpikir di kerangka lokal bagian** (+ skala): revisi "kepala lebih besar/kurang menunduk" = 1-2 angka.
8. **Penilaian butuh tampilan yang jujur:** clay abu (bukan putih/bertekstur), close-up area penting (wajah), tekstur setelah bentuk benar.
9. **Setiap QC angka wajib uji negatif; metrik pertama bisa bocor** (KC-07: luas saja lolos saat dihaluskan -> ditambah sudut lipat).
10. **Mata pengguna menangkap yang QC belum ukur** (keindahan wajah, kerapian). Setiap temuan mata -> baris di sini -> bila bisa, jadi angka.
11. **Juri banding:** referensi hasil riset + render model dari sudut kamera yang sama, berdampingan (`[[pembanding]]`). Ukur tinggi titik kunci (mata, moncong, telinga) di sumbu tegak (tidak terdistorsi sudut 3/4) lalu koreksi kerangka. Gambar banding memuat foto referensi -> hanya dikirim ke pengguna, tidak masuk repo.
12. **Diagnosis dengan varian paralel:** bila penyebab cacat tidak jelas, bangun 2 varian (matikan/ubah satu operasi) bersamaan, bandingkan; jangan menebak berulang (KC-27: dugaan pertama salah).
13. **Ukur dari sisi pengguna, ubah sedikit per putaran.** Kuda rev 6: 6 putaran banding + belasan perubahan sekaligus dari SATU sudut foto -> tiap langkah terasa membaik bagi Claude, tetapi pengguna menilai hasilnya mundur. Maks 2-3 perubahan per putaran, tunjukkan ke pengguna lebih sering, simpan versi yang disukai pengguna sebagai patokan.
14. **Tangga kesulitan:** bubut (pion, benteng) -> bubut + sedikit pahat (gajah, ratu, raja) -> organik (kuda, figurin). Naik tangga hanya setelah anak tangga sebelumnya dinilai bagus oleh pengguna.
15. **Referensi 3D > foto:** cari model 3D terbuka berlisensi (mis. glTF Sample Assets Khronos via raw GitHub, yang bisa diakses dari cloud) -> `[referensi_3d]` -> banding 3D 6 sudut, bahan & cahaya sama. Ukur proporsi (tinggi titik kunci, lebar per ketinggian) sebagai data; rancangan tetap ditulis sendiri. Kuda v2: 2 putaran sudah dekat; kuda v1 dengan 1 foto: 6 putaran tetap gagal.
16. **Detail relatif permukaan, bukan koordinat tebakan:** pakai `kedalaman` (ukir) / `tonjol` (tempel); bentuk berubah -> detail tetap menempel. Detail yang meleset dari benda = galat keras, bukan diam-diam hilang.
