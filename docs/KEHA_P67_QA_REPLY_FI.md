# KEHA P67 QA — Finnish email drafts sourced from the living evidence ledger

**Status:** The **network-access email is ready to personalize**, but the **production credential request must NOT be sent yet**.  
**Ground truth:** [KEHA P67 v2 QA test ledger](KEHA_P67_QA_TEST_LEDGER.md). Update the evidence ledger first after every test, then update these drafts.  
**Privacy:** Never copy the QA subscription key into either email. The public repository intentionally does not contain the operator's home public IPv4; insert it only in the private email to KEHA.

## 1. Reply now: confirm/open QA test host IP access

**Suggested subject:** Re: Työmarkkinatorin P67 v2 -hakurajapinta / Komplyint Oy – testiympäristön yhteysongelma ja IP-avaus

Hei,

Kiitos Komplyint Oy:lle 26.10.2026 toimitetusta Työmarkkinatorin työpaikkailmoitusten hakurajapinnan (P67 v2) testiympäristön käyttöoikeudesta.

Olemme aloittaneet SmartPloy-palvelumme teknisen QA-testauksen. Ohjelmiston sisäiset automaattiset testit ovat läpäisseet tarkistukset, mutta varsinaista API-yhteyttä testiympäristöön ei vielä saada muodostettua.

**Tähän mennessä tehdyt testit (28.10.2026):**
- Testausohjelma käynnistyy oikein, ja QA-tila sekä tilaustunnuksen olemassaolo on vahvistettu paikallisesti. Tämä ei vielä osoita, että palvelin olisi hyväksynyt tunnuksen.
- Todellinen PUBLISHED/ARCHIVED-hakutesti pysähtyy ennen HTTP-vastausta ilmoitukseen `QA_NETWORK_OR_TLS`.
- Suora HTTPS-yhteyskokeilu osoitteeseen `https://api-qa.ahtp.fi/kipa/p67/v2/jobpostings` päättyy TCP-yhteyden aikakatkaisuun noin 10 sekunnissa (`curl`-virhekoodi 28, HTTP 000). TLS-kättelyä tai API-tunnistautumista ei päästä aloittamaan.
- Vertailutesti `https://github.com` -palveluun toimii IPv4-yhteydellä (HTTP 200). KEHA:n QA-osoitteeseen yhteys ei toimi myöskään pakotetulla IPv4:llä.
- Salaisia avaimia, henkilötietoja tai hakutuloksia ei ole toimitettu ulkopuolisiin raportteihin.

**Testaavan laitteen julkinen lähtevä IPv4:** [LISÄÄ TÄHÄN VAIN KEHALLE LÄHETETTÄVÄSSÄ YKSITYISESSÄ VIESTISSÄ]

Voisitteko ystävällisesti tarkistaa, että yllä oleva osoite on sallittu QA-rajapinnan porttiin 443, ja tehdä tarvittavan IP-avauksen? Onko testiympäristön käyttöön muita verkko- tai IP-osoitevaatimuksia? Ilmoitattehan myös, tarvitaanko myöhemmin tuotantopalvelimemme erillinen lähtevä IP-osoite.

Jatkamme julkaistujen ja arkistoitujen työpaikkailmoitusten haku-, suodatus-, kieli-, tietorakenne- ja tietosuojatestien suorittamista heti, kun verkkoyhteys on käytettävissä. Toimitamme teille testiyhteenvedon, kun varsinaiset QA-testit on suoritettu.

Kiitos avustanne!

Ystävällisin terveisin,

Komplyint Oy  
info@komplyint.fi

---

## 2. Future reply: request production access ONLY after real QA acceptance

**Do not send until** P67-01 through P67-08 have real QA evidence or an explicitly agreed test scope with KEHA. Local synthetic CI success by itself is not proof of QA connectivity.

**Suggested subject:** Työmarkkinatorin P67 v2 -hakurajapinta – QA-testauksen tulokset ja tuotantotunnusten pyyntö / Komplyint Oy

Hei,

Olemme toteuttaneet Työmarkkinatorin P67 v2 -työpaikkailmoitusten hakurajapinnan testiympäristön testauksen Komplyint Oy:n SmartPloy-palvelua varten.

**Testiympäristö:** `https://api-qa.ahtp.fi/kipa/p67/v2/jobpostings`  
**Testausjakso:** [ALKU- JA LOPPUPÄIVÄMÄÄRÄ, kun tiedossa]  
**Yhteenveto:** [KIRJAA VAIN TODELLISET TULOKSET; ÄLÄ LÄHETÄ, JOS VERKKOYHTEYS EDELLEEN ESTYNYT]

| Testi | Toteutunut tulos (täytetään todennetun testin jälkeen) |
| --- | --- |
| P67-01 QA-yhteys ja tunnistautuminen | [TULOS / AIKA] |
| P67-02 Julkaistujen ilmoitusten haku | [TULOS / OSUMAMÄÄRÄ] |
| P67-03 Arkistoitujen ilmoitusten haku | [TULOS / OSUMAMÄÄRÄ] |
| P67-04 Muutosajankohdan rajaus ja tyhjät tulokset | [TULOS] |
| P67-05 Kieliversioiden käsittely | [TULOS] |
| P67-06 Työpaikkatietojen rakenteen tarkistus | [TULOS] |
| P67-07 Päivitysten, kaksoiskappaleiden ja arkistoinnin käsittely | [TULOS] |
| P67-08 Virhetilanteet, tietosuoja ja käyttöehtojen mukainen käsittely | [TULOS] |

Ohjelmiston erillisessä synteettisessä testauksessa on myös hyväksytysti suoritettu [PÄIVITÄ AJANTASAINEN TARKKA LUKU] automaattista Python/PostgreSQL-testiä sekä käyttöliittymä- ja integraatiotarkistuksia. Nämä ilmoitetaan erillisenä ohjelmiston laadunvarmistuksena, ei korvaavina rajapinnan QA-testituloksina.

Käytämme haettuja työpaikkailmoituksia vain rajapinnan käyttöehtojen sallimalla tavalla ja noudatamme alkuperäisen lähteen ilmoittamista, arkistoitujen ilmoitusten käsittelyä ja tietojen edelleenluovutusta koskevia rajoituksia.

Voisitteko vahvistaa, ovatko suoritetut testit riittävät tuotantoympäristöön siirtymiselle, ja toimittaa tuotantoympäristön erilliset käyttöoikeudet sekä mahdolliset IP-avausohjeet?

Ystävällisin terveisin,

Komplyint Oy  
info@komplyint.fi

---

## Evidence and revision procedure

- New operator receipt → append QA-00N row to [ledger](KEHA_P67_QA_TEST_LEDGER.md), preserving old failures.
- Verify each provider-backed result, note exact date/time if available, and update P67-0x outcome; distinguish zero results from connectivity failure.
- Update the appropriate Finnish email with *only verified* results.
- Keep key and private outbound IP out of public GitHub. The operator can insert the IP in a private reply directly to KEHA.
- Send the production request **only after** actual KEHA QA tests succeed and the scope is satisfactory to KEHA.
