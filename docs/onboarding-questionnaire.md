# KalviOne: College Onboarding Questionnaire

Version 1.2, 28 Nov 2026. This is a living document: see "Keeping this questionnaire up to date" at the end.

Each college answers this before KalviOne is switched on for it. Every answer becomes a setting or set-up data for that college only, so one KalviOne serves every college in its own way (D1). The Word copy that goes to colleges is built from this file.

**How to fill**

- The principal or the college's ERP coordinator fills Part A and signs Part M. Each part says who knows the answers best; pass that part to them.
- Write in the "Your answer" column. If the default suits you, write "OK".
- Questions marked *(planned)* are for modules still being built. Answer what you can; we will ask again before those modules start.
- Attach the files listed in Part L. Excel is best; a clear photo or PDF of a printed sample is fine.
- Use only real data in the copy you send us, and send it only to the KalviOne team, not on public groups.

The "Sets" column tells the KalviOne team where each answer goes. It is left out of the Word copy.

Every option a college can choose is configurable for that college (Gowtham, 28 Nov 2026). When an answer asks for something KalviOne cannot yet set, such as a different approver than the fixed role allows, the team adds a setting or feature flag for it before go-live, never a college-specific code branch (D1).

## Part A: About the college

_Who fills: principal or ERP coordinator._

| # | Question | Example or choices | Default if not answered | Sets |
| --- | --- | --- | --- | --- |
| A1 | Full name of the college, as on certificates | Pollachi College of Arts and Science | | `College.name` |
| A2 | Short code for the college (used on receipts and roll numbers) | PCAS, PIET | | `College.code` |
| A3 | Type of college | Engineering / Arts and Science / Other | | `College.college_type` |
| A4 | Affiliated or autonomous? | Affiliated / Autonomous | Affiliated | `College.affiliation_status` |
| A5 | Affiliating university | Anna University, Bharathiar University | | `College.affiliating_university` |
| A6 | College codes given by the university, AICTE, counselling (TNEA) and AISHE | Anna Univ code 7xxx, AISHE C-xxxxx | | Profile |
| A7 | Postal address, phone and official email | | | Profile |
| A8 | College logo and seal (attach a clear image) | PNG, at least 500 px wide | Name only, no logo | Profile, receipts |
| A9 | Name, mobile and email of the principal | | | First principal login |
| A10 | Name, mobile and email of the ERP coordinator (our main contact) | | | Contact |
| A11 | Does the college run shifts? Give their times | Shift I 8:30 to 1:30, Shift II 1:45 to 6:15 | One shift | Bell schedule |
| A12 | Number of students and staff today, roughly | 1,200 students, 90 staff | | Sizing |
| A13 | Language for screens, messages and printouts | English / Tamil / Both | English screens, both for parent messages | Language settings |

## Part B: Hosting, web address and outside services

_Who fills: management with the ERP coordinator or IT staff._

| # | Question | Example or choices | Default if not answered | Sets |
| --- | --- | --- | --- | --- |
| B1 | Where should KalviOne run? | On KalviOne's cloud (we run it) / On the college's own server | KalviOne's cloud | Deployment type (D2) |
| B2 | Web address for staff and students | pcas.kalvione.in / erp.pcas.edu.in (your own domain) | `<code>`.kalvione.in | `College.slug`, DNS |
| B3 | If using your own domain: who manages its DNS, and can they add a record for us? | GoDaddy, Cloudflare, college IT | | DNS |
| B4 | Own server only: machine you will use | Mac mini M4, 16 GB RAM, 512 GB SSD | We send a hardware checklist | On-prem kit |
| B5 | Own server only: internet line and speed, a fixed IP or not, and power backup (UPS, generator) | BSNL fibre 100 Mbps, UPS 2 hours | Cloudflare Tunnel, no fixed IP needed | On-prem kit |
| B6 | Own server only: who looks after it on site, and may we update it remotely? | Lab assistant, yes | Automatic updates at night | On-prem kit |
| B7 | Where should backups go, and how long should they be kept? | KalviOne cloud backup, college Google Drive | Nightly encrypted backup, 30 days | Backups |
| B8 | Email address that login, reset and invite emails come from | erp@pcas.edu.in | no-reply@kalvione.in | `DEFAULT_FROM_EMAIL` |
| B9 | Email service the college already uses | Google Workspace / Zoho Mail / Microsoft 365 / none | KalviOne's mail service | `EMAIL_URL` |
| B10 | Does the college have an SMS sender ID and DLT registration? Give the sender ID and entity ID | PCASCL, DLT entity 1201xxxx | None, WhatsApp links only | SMS provider |
| B11 | Does the college have a WhatsApp Business number or API account? | Yes, +91 9xxxx / No | None, staff send from their own phone | WhatsApp provider |
| B12 | Online fee payment: which bank or payment gateway, if any? *(planned)* | Razorpay, SBI Collect, bank's own | Counter payments only | Payment gateway |
| B13 | May KalviOne use AI features? Only questions and names of classes and fee heads are sent, never student details | Yes / No / Ask per feature | Yes | `ai_questions` per module |

## Part C: People and logins

_Who fills: principal and office._

KalviOne has these roles: Principal, HOD, Faculty, Office, Accounts, Exam cell, Student and Parent. Each role sees only its own work; an HOD sees only their own department.

| # | Question | Example or choices | Default if not answered | Sets |
| --- | --- | --- | --- | --- |
| C1 | Staff list: name, department, designation, role in KalviOne, mobile and email (attach Excel) | | | Staff accounts |
| C2 | Does every staff member have an email address they read? | Yes / Most / Few | Office adds missing ones | Invites (D25) |
| C3 | Who is the HOD of each department? | CSE: Dr. K. Ramesh | | HOD role per department |
| C4 | Who should see sensitive details (Aadhaar, community certificate, family income)? | Principal and office only | Principal and office only | Role assignments (D18) |
| C5 | Who takes fees at the counter and who manages accounts? | Two cashiers, one accountant | Accounts role | Role assignments |
| C6 | Who handles university exam work (register numbers, results)? | Exam cell, 2 staff | Exam cell role | Role assignments |
| C7 | Should students get logins now? They sign in with their roll number | Yes / Later | Later, after staff go live | Student invites |
| C8 | Should parents get logins now? *(planned, parent app)* | Yes / Later | Later | Parent invites |
| C9 | How should staff get their first password? | Email invite link / Office gives it on paper | Email invite link, valid 7 days | Invites (D25) |

## Part D: Departments, programmes and calendar

_Who fills: principal with HODs._

| # | Question | Example or choices | Default if not answered | Sets |
| --- | --- | --- | --- | --- |
| D1 | List of departments with a short code | CSE: Computer Science and Engineering | | `Department` |
| D2 | Programmes offered, with code, level, years and semesters | BE-CSE, UG, 4 years, 8 semesters | | `Programme` |
| D3 | Regulation each running batch follows | R2021 for 2023 to 2025 batches, R2025 for 2026 | | `Batch.regulation` |
| D4 | Subjects for each programme and semester: code, title, credits, type (attach the university syllabus list or Excel) | CS3401, Algorithms, 4, theory | | `Course` |
| D5 | Sections in each batch and how many students in each | II CSE: A and B, 60 each | One section A per batch | `Section` |
| D6 | Current academic year and its start and end dates | 2026-27, 1 Jul 2026 to 30 Apr 2027 | | `AcademicYear` |
| D7 | Odd and even semester start and end dates this year | Odd: 14 Jul to 20 Nov | | `Semester` |
| D8 | Lateral entry or transfer students joining in a later semester? | Yes, 2nd year BE | Supported, entered per student | `Student.entry_semester` |

## Part E: Students and admissions

_Who fills: office (admissions)._

| # | Question | Example or choices | Default if not answered | Sets |
| --- | --- | --- | --- | --- |
| E1 | Community categories used on your forms | OC, BC, BCM, MBC, SC, SCA, ST | Tamil Nadu list | `students.communities` |
| E2 | Admission quotas | Government (counselling), Management, NRI, Sports | Government and Management | `students.quotas` |
| E3 | Sanctioned seats per programme and quota this year | BE-CSE: 60 Govt, 30 Mgmt | | `Intake` |
| E4 | Roll number format, with a sample | 26CSE001 (year, dept, number) | Year, department code, 3-digit number: 26CSE001 | `students.roll_number_pattern` |
| E5 | Admission number format, with a sample | A260001 | A, year, 4-digit number: A260001 | `students.admission_number_pattern` |
| E6 | Application number format, with a sample | APP260001 | APP, year, 4-digit number: APP260001 | `students.application_number_pattern` |
| E7 | Documents collected at admission | TC, 10th and 12th marks, community, first graduate, migration | TC, 10th, 12th, community | `students.required_documents` |
| E8 | Do you keep original certificates in the office? | Yes, returned at course end / No | Recorded as collected, not held | Documents |
| E9 | Consent wording parents sign for the college to keep and use their data (attach your form if you have one) | | KalviOne's standard notice v1 | `students.consent_notice_version` |
| E10 | Who gives the university register number, and when is it entered? | University, in 2nd semester | Exam cell enters it | `Student.register_number` |
| E11 | Existing student list to load (attach Excel in any layout; we map the columns) | | | Student import (D22) |
| E12 | Do you take online applications today? From where? | College website form, Google Form | Office enters applications | Admissions |

## Part F: Fees and Tally

_Who fills: accounts with the principal._

| # | Question | Example or choices | Default if not answered | Sets |
| --- | --- | --- | --- | --- |
| F1 | Fee heads as printed on receipts, with the Tally ledger name of each, spelt exactly as in Tally | Tuition fee: "Tuition Fees"; Bus fee: "Transport Fees" | | `FeeHead` |
| F2 | Any fee heads that carry GST? Give rate and HSN/SAC code | Hostel mess 5%, SAC 9963 | None (most college fees are exempt) | `FeeHead.gst_rate` |
| F3 | GST ledger names in Tally | Output CGST, Output SGST | Output CGST, Output SGST | `fees.gst_ledgers` |
| F4 | Cash and bank accounts fees are paid into, with their Tally ledger names | Cash counter: "Cash"; SBI current a/c: "SBI CA 1234" | One cash and one bank account | `PaymentAccount` |
| F5 | Fee amounts for each batch and year, and whether they differ by quota or hostel / day scholar (attach the fee chart) | | | `FeeStructure` |
| F6 | Instalments and their due dates | Term 1 by 15 Jul, Term 2 by 15 Dec | One instalment a year | `Instalment` |
| F7 | Concessions and scholarships you give or track, and who pays each (government or college) | PMS: government; Staff ward: college | Tamil Nadu list (PMS, first graduate, 7.5%, BC/MBC, merit, staff ward, sports, management) | `fees.concession_types` |
| F8 | Who approves concessions? | Principal / Correspondent | Principal | Role assignments (D28) |
| F9 | Payment modes accepted at the counter | Cash, UPI, card, NEFT, cheque, DD | All six | Payment modes |
| F10 | Receipt number format, with a sample. Does it restart every financial year? | PCAS/2026-27/000123 | College code / financial year / 6-digit number, restarts each April | `fees.receipt_number_pattern`, `fees.financial_year_start_month` |
| F11 | Printer at the fee counter, and receipt size (attach a sample receipt) | Thermal 80 mm / A5 / A4 | A5, also opens on phone as PDF | Receipt layout |
| F12 | Tally version and edition used | TallyPrime 5 / Tally.ERP 9 | TallyPrime | Tally export |
| F13 | Company name in Tally, spelt exactly | Pollachi Educational Trust - PCAS | | `fees.tally_company` |
| F14 | Voucher type receipts should come in as, and is its numbering set to manual? | Receipt / Fee Receipt | Receipt, manual numbering | `fees.tally_voucher_type` |
| F15 | Tally groups for fee, cash, bank and tax ledgers | Fees under "Direct Incomes" | Direct Incomes, Cash-in-Hand, Bank Accounts, Duties & Taxes | `fees.tally_groups` |
| F16 | Who imports the daily Tally file, and how often? (attach a Tally ledger list export if you can) | Accountant, every evening | Daily, by the accountant | Tally routine (D26) |
| F17 | Fee reminder message wording, in English and Tamil | | KalviOne's standard wording | `fees.reminder_templates` |
| F18 | Late fee or fine rules, if any *(planned)* | ₹50 a week after due date | No fine | Planned |
| F19 | Refunds and advance payments: how do you handle them today? *(planned)* | | Not yet in KalviOne | Planned |
| F20 | Old dues still pending from earlier years (attach a list per student) | | Loaded as opening dues | Migration |

## Part G: Timetable and attendance

_Who fills: principal with HODs._

| # | Question | Example or choices | Default if not answered | Sets |
| --- | --- | --- | --- | --- |
| G1 | Does the timetable follow weekdays or a day order? If day order, how many days, and does it move on past a holiday? | Weekdays / Day order 1 to 6, moves on | Weekdays, Monday to Saturday | `attendance.cycle` |
| G2 | Which Saturdays are working days, and which timetable do they follow? | 1st and 3rd, Monday's timetable | Every Saturday, own timetable | Calendar |
| G3 | Periods each day, with start and end times, breaks and lunch (attach the bell schedule) | 7 periods, 9:15 to 4:30 | 7 (engineering), 5 (arts and science) | `PeriodSlot` |
| G4 | Holidays and non-teaching days for this semester (attach the academic calendar) | | None loaded until given | `CalendarDay` |
| G5 | Minimum attendance to sit the exam, and the condonation band | 75% eligible, 65 to 74% condonation | 75% and 65% | `attendance.limits` |
| G6 | Is the limit per subject or overall? | Per subject / Overall | Per subject (engineering), overall (arts and science) | `attendance.limits` |
| G7 | Does on duty count as present? Is medical leave left out of the total? | | On duty present; medical leave absent | `attendance.counting` |
| G8 | Is attendance taken every period, half-day or full day? | | Every period | `attendance.marking` |
| G9 | Are sections split into lab batches? How many? | B1 and B2 | Two batches where used | `LabGroup` |
| G10 | Electives taught across sections (list them) | Open elective: IoT, mixed from CSE and ECE | HOD picks the students once | `Allocation` |
| G11 | Who teaches which subject to which section (attach the workload list) | | | `Allocation` |
| G12 | How long can a teacher correct their own marking? Who corrects after that? | Same day; then HOD | Until midnight; then HOD or principal with a reason | `attendance.corrections` |
| G13 | Can any teacher mark a class they are covering, or only ones the HOD assigns? | | Any teacher of the department, with a reason | Substitutions |
| G14 | Who approves on duty and medical leave for students? | HOD / Class advisor | HOD | Leave approval |
| G15 | Rooms and labs used for classes | 5 halls, 3 labs | Rooms optional | Rooms |
| G16 | Attendance register and shortage list you print today (attach samples), and the university's format | | Monthly section register, standard layout | Reports |

## Part H: Messages to parents and students

_Who fills: principal._

| # | Question | Example or choices | Default if not answered | Sets |
| --- | --- | --- | --- | --- |
| H1 | Should parents get a message when their ward is absent? After which period? | Yes, after period 2 | Yes, after period 2, once a day | `attendance.alerts` |
| H2 | Channel for messages | WhatsApp / SMS / Both, WhatsApp first | "Open in WhatsApp" links until a provider is set up | `notify` providers |
| H3 | Language of messages | Tamil / English / Both | Both | Message templates |
| H4 | Have parents agreed to get messages? Is it on the admission form? | | Only guardians with recorded consent get messages | `Consent` |
| H5 | Other messages you send today | Fee dues, exam results, circulars, events | Absence and fee reminders only | Future templates |
| H6 | Hours when messages must not go out | Not before 7 am or after 8 pm | 7 am to 8 pm | Notify settings |

## Part I: Moving from your current software

_Who fills: ERP coordinator with office and accounts._

| # | Question | Example or choices | Default if not answered | Sets |
| --- | --- | --- | --- | --- |
| I1 | Software used today, and who supplies it | Laudea (PSG Software Technologies), Tally, Excel | | Migration plan |
| I2 | Which records should come across? | Students, guardians, staff, fees paid, dues, marks, attendance, timetable | Students, staff, current dues | Migration plan |
| I3 | How far back? | Current batches only / Last 5 years | Students on roll now, plus this year's fees | Migration plan |
| I4 | Can your supplier give an Excel or CSV export? Who has admin access to ask for it? | Yes, through the principal's login | We ask the supplier with your letter | Migration plan |
| I5 | When should KalviOne take over, and for how long should both run side by side? | From odd semester 2027, 2 weeks parallel | Start of a semester, 2 weeks parallel | Go-live date |
| I6 | Contract end date and notice period with the current supplier | 31 May 2027, 3 months | | Go-live date |
| I7 | Records kept only on paper that matter most | Old admission registers | Not loaded unless asked | Migration plan |

## Part J: Exams and marks *(being built)*

_Who fills: exam cell or COE with the principal._

| # | Question | Example or choices | Default if not answered | Sets |
| --- | --- | --- | --- | --- |
| J1 | Who sets and runs the end-semester exams? | University / College (autonomous COE) | University | `exams_autonomous` feature flag |
| J2 | Internal assessment pattern: number of tests, assignments, and how internal marks are worked out | 2 CIA tests of 50, best of 2, plus assignment, to 40 | The university preset (`load_exam_schemes`) | `SchemeComponent` |
| J3 | Internal and external marks split per subject type | Theory 40/60, practical 60/40 | The university preset | `AssessmentScheme` maximums |
| J4 | Grading scheme and pass marks (attach the regulation page) | 10-point CGPA, pass 50 | As in the regulation | `GradeScale`, `AssessmentScheme` pass rule |
| J5 | Arrears, revaluation and supplementary exams handled by the college? | | | Exams module |
| J6 | Do you print hall tickets, mark statements or provisional certificates? | | | Exams module |
| J7 | University portal you upload internal marks to, and its file format | Anna University COE portal, Excel | | Exports |
| J8 | A full copy of each regulation your running batches follow (attach the PDF or give the university link) | Anna University R2021 and R2025 | We download it from the university site | `Batch.regulation`, marks rules |
| J9 | How are internal marks rounded once added up? | Up to the next whole mark / nearest / not rounded | Up to the next whole mark | `exams.internal_rounding` |
| J10 | Codes a teacher can enter instead of a mark | AB absent, MAL malpractice, WH withheld | AB, MAL, WH (each counts as zero) | `exams.mark_codes` |

## Part K: Staff, HR, payroll and other modules *(planned)*

_Who fills: principal and accounts._

| # | Question | Example or choices | Default if not answered | Sets |
| --- | --- | --- | --- | --- |
| K1 | Staff leave types and yearly allowance | CL 12, ML 15, OD as needed | | HR module |
| K2 | Do staff mark attendance on a biometric device? Make and model | ESSL face reader | | HR module |
| K3 | How is salary worked out today, and in which software? | Tally payroll / Excel | | Payroll module |
| K4 | PF, ESI, professional tax and TDS rules that apply | PF for all, ESI for non-teaching | | Payroll module |
| K5 | Should salary go to Tally as vouchers too? | Yes, journal voucher monthly | Yes | Tally export |
| K6 | What should parents and students see in the app? | Attendance, marks, fees due, receipts, circulars | Attendance, fees, receipts | Parent app (Kalvisetu) |
| K7 | Accreditation status and next cycle | NAAC B++ till 2028; NBA for CSE, ECE | | NAAC/NBA module |
| K8 | Returns you file each year | AISHE, NIRF, UMIS, university returns | | Reports |
| K9 | Who owns each NAAC criterion, and where is the evidence kept today? | IQAC coordinator, Google Drive | | NAAC/NBA module |
| K10 | Other modules wanted, in order of need | Library, hostel, transport, placement, alumni | | Roadmap |

## Part L: Files to attach

- [ ] College logo and seal (A8)
- [ ] Staff list in Excel (C1)
- [ ] Departments, programmes and subjects per semester (D1 to D4)
- [ ] Academic calendar for this year (D6, D7, G4)
- [ ] Student list in Excel, any layout (E11)
- [ ] Blank admission form and consent form (E7, E9)
- [ ] Fee chart for each batch and quota (F5, F6)
- [ ] Sample fee receipt (F11)
- [ ] Tally ledger list export, or a screenshot of the fee and bank ledgers (F1, F4, F16)
- [ ] List of pending dues from earlier years (F20)
- [ ] Bell schedule and current timetable (G3)
- [ ] Workload list: who teaches what to whom (G11)
- [ ] Sample attendance register and shortage list (G16)
- [ ] Internal marks rules, and a full copy of each regulation (J2 to J4, J8)

## Part M: Sign-off

| # | Question | Example or choices | Default if not answered | Sets |
| --- | --- | --- | --- | --- |
| M1 | Filled by (name and designation) | | | |
| M2 | Date | | | |
| M3 | Principal's signature and college seal | | | |

## Keeping this questionnaire up to date

This section is for the KalviOne team and is left out of the Word copy.

- When a module adds a per-college setting (a key in its `config.py` `DEFAULTS`, a feature flag, or set-up data the college must give), add a question here in the same pull request, with its default.
- A new module gets its own Part before Part L. Move a *(planned)* part to a real one when its module is built, and replace its questions with the module's actual settings.
- Never renumber questions. Add new ones at the end of their part (G17, G18) and mark a dropped one "(no longer asked)", so answers already given still line up.
- Raise the version and date at the top whenever questions change, and rebuild the Word copy in the project files (`questionnaires/KalviOne - College Onboarding Questionnaire.docx`).
- Answers from each college are kept outside the repository (D10). Only the blank questionnaire lives here.
