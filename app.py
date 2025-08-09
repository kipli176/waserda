from datetime import datetime
from flask import Flask, request, render_template, redirect
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# Koneksi ke Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

sheet = client.open("poswaserda").worksheet("Data Barang")

@app.route("/barang", methods=["GET", "POST"])
def index():
    import sqlite3
    conn = sqlite3.connect("pos.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Ambil semua data dari database
    cursor.execute("SELECT * FROM barang")
    data = cursor.fetchall()

    # Deteksi ID yang sedang diedit
    edit_id = request.args.get("edit")
    item_edit = None
    if edit_id:
        cursor.execute("SELECT * FROM barang WHERE id_barang = ?", (edit_id,))
        item_edit = cursor.fetchone()

    if request.method == "POST":
        id_barang = request.form["id_barang"].strip()
        nama_barang = request.form["nama_barang"]
        satuan = request.form["satuan"]
        kategori = request.form["kategori"]

        if id_barang and id_barang.startswith("BRG"):
            # MODE EDIT
            cursor.execute("""
                UPDATE barang SET nama_barang=?, satuan=?, kategori=? WHERE id_barang=?
            """, (nama_barang, satuan, kategori, id_barang))
        else:
            # MODE TAMBAH: buat ID baru 
            new_id = generate_id("barang", "BRG", cursor)
            cursor.execute("""
                INSERT INTO barang (id_barang, nama_barang, satuan, kategori, stok_akhir)
                VALUES (?, ?, ?, ?, ?)
            """, (new_id, nama_barang, satuan, kategori, 0))

        conn.commit()
        return redirect("/barang")

    satuan_options = [
        "pcs", "bungkus", "botol", "dus", "liter", "kg", "pak", "sak", "renceng", "kaleng"
    ]
    kategori_options = [
        "Minuman", "Makanan", "Kebersihan", "Sembako", "Perlengkapan", "Gas", "Rokok", "Lainnya"
    ]

    return render_template("index.html",
                           data=data,
                           item_edit=item_edit,
                           satuan_options=satuan_options,
                           kategori_options=kategori_options)

@app.route("/pembelian", methods=["GET", "POST"])
def pembelian():
    import sqlite3
    from datetime import date

    conn = sqlite3.connect("pos.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Ambil barang untuk dropdown
    cur.execute("SELECT * FROM barang")
    barang_data = cur.fetchall()
    barang_options = [{"id": row["id_barang"], "nama": row["nama_barang"], "stok": row["stok_akhir"], "satuan": row["satuan"]} for row in barang_data]

    # Tambah stok ke kolom stok_akhir
    def tambah_stok_akhir(id_barang, jumlah):
        cur.execute("SELECT stok_akhir FROM barang WHERE id_barang = ?", (id_barang,))
        row = cur.fetchone()
        stok_lama = row["stok_akhir"] if row else 0
        stok_baru = stok_lama + jumlah
        cur.execute("UPDATE barang SET stok_akhir = ? WHERE id_barang = ?", (stok_baru, id_barang))

    def kurangi_stok_akhir(id_barang, jumlah):
        cur.execute("SELECT stok_akhir FROM barang WHERE id_barang = ?", (id_barang,))
        row = cur.fetchone()
        stok_lama = row["stok_akhir"] if row else 0
        stok_baru = max(0, stok_lama - jumlah)
        cur.execute("UPDATE barang SET stok_akhir = ? WHERE id_barang = ?", (stok_baru, id_barang))

    # Ambil semua pembelian
    now = datetime.today()
    bulan = f"{now.month:02d}"   # Format dua digit, misalnya '08'
    tahun = str(now.year)        # Misalnya '2025'

    # Query berdasarkan bulan dan tahun saat ini
    cur.execute("""
        SELECT * FROM pembelian
        WHERE strftime('%m', tanggal) = ? AND strftime('%Y', tanggal) = ?
    """, (bulan, tahun)) 
    pembelian_data = cur.fetchall()

    # MODE EDIT
    item_edit = None
    edit_id = request.args.get("edit")
    if edit_id:
        cur.execute("SELECT * FROM pembelian WHERE id_pembelian = ?", (edit_id,))
        item_edit = cur.fetchone()

    # POST: TAMBAH / EDIT
    if request.method == "POST":
        id_barang = request.form["id_barang"]
        jumlah = int(request.form["jumlah"])
        harga = int(request.form["harga_beli"])
        keterangan = request.form.get("keterangan", "")
        total = jumlah * harga
        today = str(date.today())

        # Ambil nama_barang
        nama_barang = next((b["nama"] for b in barang_options if b["id"] == id_barang), "Tidak ditemukan")

        id_pembelian = request.form.get("id_pembelian")
        if id_pembelian and id_pembelian.startswith("PB"):
            # MODE EDIT
            cur.execute("SELECT * FROM pembelian WHERE id_pembelian = ?", (id_pembelian,))
            row = cur.fetchone()
            if row:
                id_barang_lama = row["id_barang"]
                jumlah_lama = row["jumlah"]
                kurangi_stok_akhir(id_barang_lama, jumlah_lama)

                cur.execute("""
                    UPDATE pembelian
                    SET tanggal=?, id_barang=?, nama_barang=?, jumlah=?, harga_beli=?, total_beli=?, keterangan=?
                    WHERE id_pembelian=?
                """, (today, id_barang, nama_barang, jumlah, harga, total, keterangan, id_pembelian))

                tambah_stok_akhir(id_barang, jumlah)

        else:
            # MODE TAMBAH: generate ID baru 
            new_id = generate_id("pembelian", "PB", cur)
            cur.execute("""
                INSERT INTO pembelian (id_pembelian, tanggal, id_barang, nama_barang,
                                       jumlah, harga_beli, total_beli, keterangan)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (new_id, today, id_barang, nama_barang, jumlah, harga, total, keterangan))

            tambah_stok_akhir(id_barang, jumlah)

        conn.commit()
        return redirect("/pembelian")

    return render_template("pembelian.html",
                           barang_options=barang_options,
                           pembelian_data=pembelian_data,
                           item_edit=item_edit)


def generate_id(table, prefix, cur):
    cur.execute(f"SELECT id_{table} FROM {table} WHERE id_{table} LIKE '{prefix}%'")
    existing = [int(row[0][len(prefix):]) for row in cur.fetchall()]
    new_num = max(existing) + 1 if existing else 1
    return f"{prefix}{new_num:03d}"


def format_wa_nota(tanggal, nama_pelanggan, nomor_wa, item_list, total, catatan):
    lines = [
        "🧾 *NOTA WASERDA*",
        f"Tanggal: {tanggal}",
        f"Pelanggan: {nama_pelanggan} ({nomor_wa})",
        f"Catatan: {catatan}",
        "",
        "Daftar Belanja:"
    ]
    for item in item_list:
        nama = item['nama']
        jumlah = item['jumlah']
        harga = item['harga']
        subtotal = jumlah * harga
        lines.append(f"- {nama} x{jumlah} @{harga:,} = {subtotal:,}")

    lines.append("")
    lines.append(f"Total: Rp{total:,}")
    lines.append("Terima kasih 🙏")

    return "\n".join(lines)

import requests

def kirim_wa(nomor_wa, pesan):
    endpoint = "http://194.163.184.129:3001/send-message"
    payload = {
        "number": nomor_wa,
        "message": pesan
    }
    try:
        response = requests.post(endpoint, json=payload)
        return response.status_code == 200
    except Exception as e:
        print("Gagal kirim WA:", e)
        return False
    
def format_rupiah(angka):
    return f"Rp {angka:,.0f}".replace(",", ".")

app.jinja_env.filters["rupiah"] = format_rupiah

@app.route("/", methods=["GET", "POST"])
@app.route("/penjualan", methods=["GET", "POST"])
def penjualan():
    import sqlite3
    from datetime import date

    conn = sqlite3.connect("pos.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Ambil data referensi
    cur.execute("SELECT * FROM pelanggan")
    pelanggan_data = cur.fetchall()
    pelanggan_dict = {row["id_pelanggan"]: {"nama": row["nama"], "wa": row["wa"]} for row in pelanggan_data}

    cur.execute("SELECT * FROM barang")
    barang_data = cur.fetchall()
    barang_dict = {row["id_barang"]: row for row in barang_data}

    cur.execute("SELECT * FROM pembelian ORDER BY tanggal ASC")
    pembelian_data = cur.fetchall()

    # FIFO untuk HPP
    def hitung_hpp_fifo(id_barang, jumlah_jual):
        stok = [(row["jumlah"], row["harga_beli"]) for row in pembelian_data if row["id_barang"] == id_barang]
        total_hpp = 0
        sisa = jumlah_jual
        for qty, harga in stok:
            ambil = min(sisa, qty)
            total_hpp += ambil * harga
            sisa -= ambil
            if sisa == 0:
                break
        if jumlah_jual == 0:
            return 0
        return round(total_hpp / jumlah_jual)

    # FORM SUBMIT
    if request.method == "POST":
        edit_id = request.form.get("edit_id")
        is_edit = bool(edit_id)

        id_penjualan = edit_id if is_edit else generate_id("penjualan", "PJ", cur)

        id_pelanggan = request.form["id_pelanggan"]
        id_barang_list = request.form.getlist("id_barang[]")
        jumlah_list = request.form.getlist("jumlah[]")
        harga_list = request.form.getlist("harga_jual[]")
        catatan = request.form["catatan"]
        tanggal = str(date.today())

        # Jika EDIT, kembalikan stok dulu & hapus penjualan lama
        if is_edit:
            cur.execute("SELECT * FROM penjualan WHERE id_penjualan=?", (id_penjualan,))
            rows_lama = cur.fetchall()
            for row in rows_lama:
                cur.execute("UPDATE barang SET stok_akhir = stok_akhir + ? WHERE id_barang = ?", (row["jumlah"], row["id_barang"]))
            cur.execute("DELETE FROM penjualan WHERE id_penjualan=?", (id_penjualan,))

        item_list = []
        total_all = 0

        for id_barang, jumlah_str, harga_str in zip(id_barang_list, jumlah_list, harga_list):
            jumlah = int(jumlah_str)
            harga_jual = int(harga_str)
            nama_barang = barang_dict[id_barang]["nama_barang"]
            total = jumlah * harga_jual
            hpp_unit = hitung_hpp_fifo(id_barang, jumlah)
            laba = (harga_jual - hpp_unit) * jumlah

            # Tambahkan ke tabel
            cur.execute("""
                INSERT INTO penjualan (id_penjualan, tanggal, id_pelanggan, id_barang, nama_barang,
                jumlah, harga_jual, total, catatan, hpp_unit, laba)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (id_penjualan, tanggal, id_pelanggan, id_barang, nama_barang,
                  jumlah, harga_jual, total, catatan, hpp_unit, laba))

            # Kurangi stok
            cur.execute("UPDATE barang SET stok_akhir = stok_akhir - ? WHERE id_barang = ?", (jumlah, id_barang))

            item_list.append({"nama": nama_barang, "jumlah": jumlah, "harga": harga_jual})
            total_all += total

        conn.commit()

        # Kirim nota
        nama_pelanggan = pelanggan_dict.get(id_pelanggan, {}).get("nama", "Tidak Dikenal")
        nomor_wa = pelanggan_dict.get(id_pelanggan, {}).get("wa", "")
        nota = format_wa_nota(tanggal, nama_pelanggan, nomor_wa, item_list, total_all, catatan)
        kirim_wa(nomor_wa, nota)

        return redirect("/penjualan")

    # TAMBAH / EDIT FORM
    if request.args.get("tambah") or request.args.get("edit"):
        barang_tersedia = [b for b in barang_data if b["stok_akhir"] > 0]
        harga_terakhir = {}
        for row in reversed(pembelian_data):
            idb = row["id_barang"]
            if idb not in harga_terakhir:
                harga_terakhir[idb] = row["harga_beli"]

        if request.args.get("edit"):
            edit_id = request.args.get("edit")
            cur.execute("SELECT * FROM penjualan WHERE id_penjualan = ?", (edit_id,))
            rows = cur.fetchall()
            if not rows:
                return "Transaksi tidak ditemukan"
            id_pelanggan = rows[0]["id_pelanggan"]
            catatan = rows[0]["catatan"]
            return render_template("penjualan_form.html",
                                   pelanggan_data=pelanggan_data,
                                   barang_data=barang_data,
                                   harga_terakhir=harga_terakhir,
                                   edit=True,
                                   id_penjualan=edit_id,
                                   selected_pelanggan=id_pelanggan,
                                   catatan=catatan,
                                   baris=rows)
        else:
            return render_template("penjualan_form.html",
                                   pelanggan_data=pelanggan_data,
                                   barang_data=barang_tersedia,
                                   harga_terakhir=harga_terakhir)

    # LIHAT NOTA
    if request.args.get("lihat"):
        lihat_id = request.args.get("lihat")
        cur.execute("SELECT * FROM penjualan WHERE id_penjualan = ?", (lihat_id,))
        rows = cur.fetchall()
        if not rows:
            return "Transaksi tidak ditemukan"

        tanggal = rows[0]["tanggal"]
        id_pelanggan = rows[0]["id_pelanggan"]
        nama_pelanggan = pelanggan_dict.get(id_pelanggan, {}).get("nama", "Tidak Dikenal")
        catatan = rows[0]["catatan"]

        item_list = []
        total_all = 0
        for row in rows:
            item_list.append({
                "nama": row["nama_barang"],
                "jumlah": row["jumlah"],
                "harga": row["harga_jual"]
            })
            total_all += row["total"]

        return render_template("nota_penjualan.html",
                               id_penjualan=lihat_id,
                               tanggal=tanggal,
                               nama_pelanggan=nama_pelanggan,
                               catatan=catatan,
                               item_list=item_list,
                               total=total_all)
    
        # TAMPILKAN RINGKASAN TRANSAKSI
    now = datetime.today()
    bulan = f"{now.month:02d}"   # Format dua digit, misalnya '08'
    tahun = str(now.year)        # Misalnya '2025'

    # Query berdasarkan bulan dan tahun saat ini
    cur.execute("""
        SELECT * FROM penjualan
        WHERE strftime('%m', tanggal) = ? AND strftime('%Y', tanggal) = ?
    """, (bulan, tahun))
    rows = cur.fetchall()
    transaksi_dict = {}
    for row in rows:
        id_trans = row["id_penjualan"]
        total = row["total"]
        if id_trans not in transaksi_dict:
            transaksi_dict[id_trans] = {
                "tanggal": row["tanggal"],
                "id_pelanggan": row["id_pelanggan"],
                "nama_pelanggan": pelanggan_dict.get(row["id_pelanggan"], {}).get("nama", "Tidak Dikenal"),
                "total": total
            }
        else:
            transaksi_dict[id_trans]["total"] += total

    return render_template("penjualan.html", transaksi=transaksi_dict)

@app.route("/laporan")
def laporan():
    import sqlite3
    import datetime
    from collections import defaultdict
    from flask import request, render_template

    conn = sqlite3.connect("pos.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    today = datetime.date.today()
    bulan = request.args.get("bulan", f"{today.month:02d}")
    tahun = request.args.get("tahun", str(today.year))

    # === TOTAL MODAL ===
    cur.execute("""
        SELECT * FROM pemodal
        WHERE strftime('%m', tanggal) = ? AND strftime('%Y', tanggal) = ?
    """, (bulan, tahun))
    pemodal_data = cur.fetchall()
    total_modal = sum(row["jumlah"] for row in pemodal_data)

    # === TOTAL PENGELUARAN ===
    cur.execute("""
        SELECT * FROM pengeluaran
        WHERE strftime('%m', tanggal) = ? AND strftime('%Y', tanggal) = ?
    """, (bulan, tahun))
    pengeluaran_data = cur.fetchall()
    total_pengeluaran = sum(row["jumlah"] for row in pengeluaran_data)

    # === PENJUALAN ===
    cur.execute("""
        SELECT * FROM penjualan
        WHERE strftime('%m', tanggal) = ? AND strftime('%Y', tanggal) = ?
    """, (bulan, tahun))
    penjualan_data = cur.fetchall()

    total_penjualan = 0
    total_laba = 0
    ringkasan_harian = defaultdict(lambda: {"penjualan": 0, "laba": 0})

    for row in penjualan_data:
        tanggal = row["tanggal"]
        total_penjualan += row["total"]
        total_laba += row["laba"]
        ringkasan_harian[tanggal]["penjualan"] += row["total"]
        ringkasan_harian[tanggal]["laba"] += row["laba"]

    # === NILAI BARANG ===
    cur.execute("SELECT * FROM barang")
    barang_data = cur.fetchall()

    cur.execute("""
        SELECT * FROM pembelian
        WHERE strftime('%m', tanggal) = ? AND strftime('%Y', tanggal) = ?
        ORDER BY tanggal DESC
    """, (bulan, tahun))
    pembelian_data = cur.fetchall()

    harga_beli_terakhir = {}
    for row in pembelian_data:
        idb = row["id_barang"]
        if idb not in harga_beli_terakhir:
            harga_beli_terakhir[idb] = row["harga_beli"]

    kas_manual = 0
    total_nilai_barang = 0

    for row in barang_data:
        idb = row["id_barang"]
        nama = row["nama_barang"].upper()
        stok = row["stok_akhir"]
        harga = harga_beli_terakhir.get(idb, 0)
        subtotal = stok * harga

        if "KAS" in nama:
            kas_manual += subtotal
        else:
            total_nilai_barang += subtotal

    pengeluaran_dari_kas = min(kas_manual, total_pengeluaran)
    pengeluaran_dari_pemodal = total_pengeluaran - pengeluaran_dari_kas

    # === MODAL BELANJA BARANG ===
    modal_belanja = total_modal - pengeluaran_dari_pemodal

    # === PERHITUNGAN KAS AKHIR SAAT INI ===
    sisa_kas1 = modal_belanja - total_nilai_barang
    # === PERHITUNGAN KAS AKHIR SAAT INI ===
    sisa_kas2 = modal_belanja - total_nilai_barang + total_laba

    # === BAGI HASIL ===
    bagian_kamu = bagian_kas = bagian_pemodal = 0
    if total_laba > 0:
        bagian_kamu = round(total_laba * 0.30)
        bagian_kas = round(total_laba * 0.35)
        bagian_pemodal = total_laba - bagian_kamu - bagian_kas

    return render_template("laporan.html",
        bulan=bulan,
        tahun=tahun,
        total_modal=total_modal,
        total_pengeluaran=total_pengeluaran,
        pengeluaran_dari_kas=pengeluaran_dari_kas,
        pengeluaran_dari_pemodal=pengeluaran_dari_pemodal,
        modal_belanja=modal_belanja,
        total_nilai_barang=total_nilai_barang,
        total_penjualan=total_penjualan,
        total_laba=total_laba,
        sisa_kas1=sisa_kas1,
        sisa_kas2=sisa_kas2,
        bagian_kamu=bagian_kamu,
        bagian_kas=bagian_kas,
        kas_manual=kas_manual,
        bagian_pemodal=bagian_pemodal,
        ringkasan=sorted(ringkasan_harian.items())
    )




@app.route("/pelanggan", methods=["GET", "POST"])
def pelanggan():
    import sqlite3
    conn = sqlite3.connect("pos.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Ambil semua data
    cur.execute("SELECT * FROM pelanggan")
    rows = cur.fetchall()

    if request.method == "POST":
        id_pelanggan = request.form.get("id_pelanggan")
        nama = request.form["nama"]
        wa = request.form["wa"]

        if request.form.get("mode") == "edit":
            cur.execute("""
                UPDATE pelanggan SET nama = ?, wa = ? WHERE id_pelanggan = ?
            """, (nama, wa, id_pelanggan))
        else:
            # Buat ID otomatis 
            new_id = generate_id("pelanggan", "PL", cur)

            # Insert data baru
            cur.execute("INSERT INTO pelanggan (id_pelanggan, nama, wa) VALUES (?, ?, ?)",
                        (new_id, nama, wa))

        conn.commit()
        return redirect("/pelanggan")

    # Jika klik edit
    item_edit = None
    edit_id = request.args.get("edit")
    if edit_id:
        cur.execute("SELECT * FROM pelanggan WHERE id_pelanggan = ?", (edit_id,))
        item_edit = cur.fetchone()

    return render_template("pelanggan.html", rows=rows, item_edit=item_edit)

@app.route("/pengeluaran", methods=["GET", "POST"])
def pengeluaran():
    import sqlite3
    from datetime import date

    conn = sqlite3.connect("pos.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    kategori_list = ["Listrik", "Sewa", "Bensin", "ATK", "Gaji", "Lainnya"]

    # Ambil semua data
    cur.execute("SELECT * FROM pengeluaran")
    rows = cur.fetchall()

    if request.method == "POST":
        id_pengeluaran = request.form.get("id_pengeluaran")
        tanggal = request.form["tanggal"]
        kategori = request.form["kategori"]
        jumlah = int(request.form["jumlah"])
        keterangan = request.form.get("keterangan", "")

        if request.form.get("mode") == "edit":
            cur.execute("""
                UPDATE pengeluaran SET tanggal=?, kategori=?, jumlah=?, keterangan=?
                WHERE id_pengeluaran=?
            """, (tanggal, kategori, jumlah, keterangan, id_pengeluaran))
        else:
            # Buat ID otomatis
            new_id = generate_id("pengeluaran", "OUT", cur)

            cur.execute("""
                INSERT INTO pengeluaran (id_pengeluaran, tanggal, kategori, jumlah, keterangan)
                VALUES (?, ?, ?, ?, ?)
            """, (new_id, tanggal, kategori, jumlah, keterangan))

        conn.commit()
        return redirect("/pengeluaran")

    # Edit jika ada
    item_edit = None
    edit_id = request.args.get("edit")
    if edit_id:
        cur.execute("SELECT * FROM pengeluaran WHERE id_pengeluaran = ?", (edit_id,))
        item_edit = cur.fetchone()

    return render_template("pengeluaran.html",
                           rows=rows,
                           item_edit=item_edit,
                           kategori_list=kategori_list,
                           today=str(date.today()))


@app.route("/pemodal", methods=["GET", "POST"])
def pemodal():
    import sqlite3
    from datetime import date

    conn = sqlite3.connect("pos.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Ambil semua data
    now = datetime.today()
    bulan = f"{now.month:02d}"   # Format dua digit, misalnya '08'
    tahun = str(now.year)        # Misalnya '2025'

    # Query berdasarkan bulan dan tahun saat ini
    cur.execute("""
        SELECT * FROM pemodal
        WHERE strftime('%m', tanggal) = ? AND strftime('%Y', tanggal) = ?
    """, (bulan, tahun)) 
    rows = cur.fetchall()

    if request.method == "POST":
        id_pemodal = request.form.get("id_pemodal")
        nama = request.form["nama"]
        jumlah = int(request.form["jumlah"])
        tanggal = request.form["tanggal"]

        if request.form.get("mode") == "edit":
            cur.execute("""
                UPDATE pemodal SET nama=?, jumlah=?, tanggal=? WHERE id_pemodal=?
            """, (nama, jumlah, tanggal, id_pemodal))
        else: 
            new_id = generate_id("pemodal", "PM", cur)

            cur.execute("""
                INSERT INTO pemodal (id_pemodal, nama, jumlah, tanggal)
                VALUES (?, ?, ?, ?)
            """, (new_id, nama, jumlah, tanggal))

        conn.commit()
        return redirect("/pemodal")

    # Edit
    item_edit = None
    edit_id = request.args.get("edit")
    if edit_id:
        cur.execute("SELECT * FROM pemodal WHERE id_pemodal = ?", (edit_id,))
        item_edit = cur.fetchone()

    return render_template("pemodal.html",
                           rows=rows,
                           item_edit=item_edit,
                           today=str(date.today()))


if __name__ == "__main__":
    app.run(debug=True)
