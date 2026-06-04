"""Generate fact-dense sample PDFs for testing socratic, across domains.

Uses PyMuPDF's Story API to flow HTML content across multiple pages.
Run from the agent venv:  uv run --project agent python samples/generate_samples.py
"""
from pathlib import Path

import pymupdf

OUT = Path(__file__).parent

_CSS = """
h1 { font-size: 20px; margin-bottom: 4px; }
h2 { font-size: 14px; margin-top: 14px; margin-bottom: 2px; color: #222; }
p  { font-size: 11px; line-height: 1.5; margin: 4px 0; text-align: justify; }
li { font-size: 11px; line-height: 1.45; }
"""

DOCS: dict[str, str] = {
    "medical_hypertension.pdf": """
<h1>Hypertension: Pathophysiology, Diagnosis, and Management</h1>
<p>Hypertension, commonly called high blood pressure, is a chronic condition in which the
force of blood against the arterial walls is persistently elevated. It is one of the leading
modifiable risk factors for cardiovascular disease worldwide and is often called the
&ldquo;silent killer&rdquo; because it frequently produces no symptoms until target-organ
damage has occurred.</p>

<h2>Classification of Blood Pressure</h2>
<p>Blood pressure is recorded as two numbers: systolic pressure (during heart contraction)
over diastolic pressure (during relaxation), measured in millimeters of mercury (mmHg).
Under the 2017 ACC/AHA guideline, blood pressure is categorized as follows. Normal is below
120/80 mmHg. Elevated is a systolic of 120 to 129 with a diastolic below 80. Stage 1
hypertension is 130 to 139 systolic or 80 to 89 diastolic. Stage 2 hypertension is at or
above 140 systolic or 90 diastolic. A hypertensive crisis is a reading above 180/120 mmHg
and requires prompt medical attention.</p>

<h2>Pathophysiology</h2>
<p>Arterial pressure is the product of cardiac output and systemic vascular resistance. Any
factor that increases either of these raises blood pressure. A central regulator is the
renin&ndash;angiotensin&ndash;aldosterone system (RAAS). The kidneys release renin, which
converts angiotensinogen to angiotensin I. Angiotensin-converting enzyme (ACE) then converts
angiotensin I to angiotensin II, a potent vasoconstrictor. Angiotensin II also stimulates the
release of aldosterone, which promotes sodium and water retention, increasing blood volume.
The sympathetic nervous system contributes by increasing heart rate and vasoconstriction.</p>

<h2>Primary vs Secondary Hypertension</h2>
<p>Roughly 90 to 95 percent of cases are primary (also called essential) hypertension, which
has no single identifiable cause and develops gradually over years. The remaining 5 to 10
percent are secondary hypertension, caused by an underlying condition such as chronic kidney
disease, renal artery stenosis, primary aldosteronism, pheochromocytoma, or the use of certain
medications. Identifying secondary causes matters because treating the root condition can cure
the hypertension.</p>

<h2>Risk Factors and Complications</h2>
<p>Major risk factors include advancing age, obesity, a high-sodium diet, excessive alcohol
intake, physical inactivity, smoking, and family history. Left untreated, sustained
hypertension damages organs over time, leading to stroke, myocardial infarction, heart
failure, chronic kidney disease, and hypertensive retinopathy.</p>

<h2>Management</h2>
<p>First-line management emphasizes lifestyle modification: the DASH diet (rich in fruits,
vegetables, and low-fat dairy), reducing dietary sodium to under 2.3 grams per day, regular
aerobic exercise, weight loss, and moderation of alcohol. When medication is required, common
first-line drug classes are thiazide diuretics, ACE inhibitors, angiotensin II receptor
blockers (ARBs), and calcium channel blockers. ACE inhibitors and ARBs are particularly
favored in patients with diabetes or chronic kidney disease because they protect the kidneys.
Therapy is individualized, and many patients require a combination of two or more agents to
reach their target blood pressure.</p>
""",
    "cs_tcp_udp.pdf": """
<h1>The Transport Layer: TCP and UDP</h1>
<p>The transport layer sits above the network layer in the TCP/IP model and provides
end-to-end communication services for applications. Its two dominant protocols, the
Transmission Control Protocol (TCP) and the User Datagram Protocol (UDP), offer very different
trade-offs between reliability and speed. Both use 16-bit port numbers, ranging from 0 to
65535, to direct data to the correct application process on a host.</p>

<h2>Transmission Control Protocol (TCP)</h2>
<p>TCP is connection-oriented, reliable, and delivers a byte stream in order. Before any data
is exchanged, the two endpoints establish a connection using a three-way handshake: the client
sends a SYN segment, the server replies with a SYN-ACK, and the client confirms with an ACK.
TCP guarantees reliable delivery by assigning a sequence number to each byte and requiring the
receiver to return acknowledgments. If an acknowledgment is not received within a timeout, the
sender retransmits the lost data. The standard TCP header is 20 bytes long.</p>

<h2>Flow Control and Congestion Control</h2>
<p>TCP uses a sliding window mechanism for flow control, which prevents a fast sender from
overwhelming a slow receiver by limiting how much unacknowledged data may be in flight.
Separately, congestion control prevents the sender from overwhelming the network itself. It
begins with slow start, in which the congestion window grows exponentially until a threshold
is reached, after which it enters congestion avoidance and grows linearly. The widely used
strategy of increasing the window slowly and halving it on loss is known as additive-increase,
multiplicative-decrease (AIMD).</p>

<h2>User Datagram Protocol (UDP)</h2>
<p>UDP is connectionless and unreliable: it sends independent packets called datagrams with no
handshake, no acknowledgments, no retransmission, and no guarantee of ordering. This makes it
faster and lower-overhead than TCP. The UDP header is only 8 bytes, compared with TCP&rsquo;s
20 bytes. Because it avoids the latency of connection setup and reliability machinery, UDP is
preferred for applications that value speed over perfect delivery, such as the Domain Name
System (DNS), live video and audio streaming, voice over IP (VoIP), and online gaming.</p>

<h2>Choosing Between Them</h2>
<p>The choice depends on application requirements. Use TCP when every byte must arrive
correctly and in order&mdash;for example, web pages (HTTP), email, and file transfer. Use UDP
when occasional loss is acceptable but low latency is critical. Some modern protocols, such as
QUIC, build reliability features on top of UDP to get the best of both worlds.</p>
""",
    "finance_time_value_money.pdf": """
<h1>The Time Value of Money</h1>
<p>The time value of money is one of the most fundamental concepts in finance. It states that
a sum of money available today is worth more than the same sum in the future, because money
available now can be invested to earn a return. This single idea underpins the valuation of
loans, investments, bonds, and businesses.</p>

<h2>Future Value and Present Value</h2>
<p>Future value (FV) measures what a present sum will grow to after earning interest. With
compound interest, the future value of a present amount (PV) invested for n periods at an
interest rate r per period is FV = PV times (1 + r) raised to the power n. Present value runs
the calculation in reverse: it is the value today of a future cash flow, computed as
PV = FV divided by (1 + r) to the power n. The interest rate used to translate future cash
flows into present value is called the discount rate.</p>

<h2>Simple vs Compound Interest</h2>
<p>Simple interest is calculated only on the original principal, so it grows linearly. Compound
interest is calculated on the principal plus all previously accumulated interest, so it grows
exponentially&mdash;interest earns interest. The more frequently interest is compounded
(annually, quarterly, monthly, or daily), the greater the final amount. A useful shortcut is
the Rule of 72: dividing 72 by the annual percentage interest rate gives the approximate number
of years for an investment to double. For example, at 8 percent, money doubles in roughly nine
years.</p>

<h2>Annuities</h2>
<p>An annuity is a series of equal cash flows made at regular intervals. In an ordinary annuity,
payments occur at the end of each period; in an annuity due, payments occur at the beginning of
each period. Because each payment in an annuity due is received one period earlier, an annuity
due always has a higher present value than an otherwise identical ordinary annuity.</p>

<h2>Net Present Value</h2>
<p>Net present value (NPV) applies these principles to investment decisions. It discounts all of
a project&rsquo;s expected future cash flows back to the present using the discount rate and
subtracts the initial investment. A positive NPV indicates that a project is expected to add
value and is generally worth pursuing, while a negative NPV suggests it would destroy value.</p>
""",
    "astronomy_star_lifecycle.pdf": """
<h1>The Life Cycle of Stars</h1>
<p>Stars are born, live, and die over timescales of millions to trillions of years. A
star&rsquo;s entire life is a balance between two opposing forces: the inward pull of gravity
and the outward push of radiation pressure from nuclear fusion in its core. The mass of a star
at birth is the single most important factor determining its life cycle and ultimate fate.</p>

<h2>Star Formation</h2>
<p>Stars form inside vast clouds of gas and dust called nebulae. When a region of a nebula
becomes dense enough, gravity causes it to collapse into a hot, spinning core called a
protostar. As the core contracts, its temperature and pressure rise. When the core reaches
about 10 million kelvin, nuclear fusion of hydrogen into helium ignites, and a true star is
born.</p>

<h2>The Main Sequence</h2>
<p>For most of its life, a star is on the main sequence, steadily fusing hydrogen into helium
in its core. During this phase the star is in hydrostatic equilibrium: the outward radiation
pressure from fusion exactly balances the inward force of gravity. The main sequence is the
longest stage of a star&rsquo;s life; our Sun, for example, will spend roughly 10 billion years
on it. More massive stars burn their fuel far faster and have much shorter lives.</p>

<h2>The Fate of Low-Mass Stars</h2>
<p>When a low-mass star like the Sun exhausts the hydrogen in its core, the core contracts and
the outer layers expand and cool, turning the star into a red giant. Eventually the outer
layers are gently expelled into space, forming a glowing shell called a planetary nebula. What
remains is a small, dense, hot core called a white dwarf, which slowly cools over billions of
years.</p>

<h2>The Fate of High-Mass Stars</h2>
<p>Stars more than about eight times the mass of the Sun follow a more violent path. They swell
into red supergiants and fuse progressively heavier elements, building up to iron in their
cores. Because fusing iron consumes rather than releases energy, the core collapses
catastrophically and the star explodes as a supernova. The collapsed remnant becomes either a
neutron star or, if the original star was massive enough, a black hole. The maximum mass of a
stable white dwarf, about 1.4 times the mass of the Sun, is known as the Chandrasekhar limit.</p>
""",
}


def build(filename: str, html: str) -> int:
    story = pymupdf.Story(html=html, user_css=_CSS)
    writer = pymupdf.DocumentWriter(str(OUT / filename))
    mediabox = pymupdf.paper_rect("letter")
    where = mediabox + (54, 54, -54, -54)
    pages = 0
    more = 1
    while more:
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
        pages += 1
    writer.close()
    return pages


if __name__ == "__main__":
    for name, html in DOCS.items():
        n = build(name, html)
        print(f"  {name}: {n} pages")
    print(f"Wrote {len(DOCS)} sample PDFs to {OUT}")
