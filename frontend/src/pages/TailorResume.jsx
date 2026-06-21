// /tailor-resume renders the resume-tailoring workspace. Job cards deep-link
// here with ?job_url=… so the JD auto-extracts; the page tailors the résumé,
// scores ATS coverage, shows a diff, and exports a PDF.
//
// NOTE: A fuller "Peregrine Quill"-style section editor (Keep/Skip/Edit + live
// paginated preview + Cover Letter / HR Email tabs) lives in the standalone
// ArpanCharola/PeregrineQuill app (Next.js/TS). Porting it here is a larger,
// separate effort tracked as a follow-up — this page is the working tailor flow.
export { default } from "./TailoredResumes";
