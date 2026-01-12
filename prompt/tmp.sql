

-- 2. passages
INSERT INTO passages (
    part_id, passage_title, passage_text, passage_order
) VALUES (
    30, '', 'High school students eager to stand out in the college application process often participate in a litany of extracurricular activities hoping to bolster their chances of admission a selective undergraduate institution.

However, college admissions experts say that the quality of a college hopeful''s extracurricular activities matter more than the number of activities. he or she participates in.

Sue Rexford, the director of college guidance at the Charles. E. Smith Jewish Day School , says it is not necessary for a student, filling out the Common Application to list lo activities in the application

"No" college will expect that a students has a huge laundry list of extracurriculars that they have been passionately involved in each for an tended period of time, " Rexfon d wrote in an email.

Experts say it is toughen to distinguish oneself in a school-affiliated extracurricular activity that is common among high school students than it is to stand out while doing an uncommon activity.

The competition to stand out and make an impact is going to be much stiffer, and so if they ''re going to do a popular activity, I''d say, be the best at it."says Sara Harherson, a college admission consultant.

High school students who have an impressive personal project they are working on independently often impress colleges, experts say.

"For example, a student with an interest in entrepreneurship could demonstrate skills and potential by starting a profitable small business." Olivia Valdes, the founder or Zen Admissions consulting firm, wrote in an email.

Josoph Adegboyega-Edun, a Maryland High school guidance counselor, says unconventional, extracurricular activities can help students, impress college admissions offices, assuming they demonstrated, serious commitment."Again, since one of the big question. high school seniors muse consider is"What makes you unique?" having an uncommon, extracurricular activity, a conventional one is an advantage,"he wrote in an email.

Experts say demonstrating talent in at least one extracurricular activity can help in the college admissions process, especially at top-tier undergraduate institutions.

"Distinguishing yourself in one focused type of extracurricular activity can be a positive in the admissions process, especially for highly selective institutions, 431 where having top grades and test scores is not enough,"Katie Kelley admissions counselor at Ivy Wise admissions consultancy, wrote in an email."Students need to have that quality or hook that will appeal to admissions officers and allow them to visualize how the student might come and enrich their campus community."

Extracurricular activities related to the college major declared on a college application are beneficial, experts suggest."If you already know your major, having an extracurricular that fits into that major can be a big plus,"says Mayghin Levine, the manager of educational opportunities with The Cabbage Patch Settlement House, a Louisville, Kentucky, nonprofit community center.

High school students who have had a strong positive influence on their community through an extracurricular activity may impress a college and win a scholarship, says Erica Gwyn, a former math and science magnet program assistant at a public high school who is now executive director of the Kaleidoscope Careers Academy in Atlanta, a nonprofit organization.', 2
)
RETURNING id;
-- 假设 passage_id=3

-- 3. questions (5题)
-- ...existing code...

-- 3. questions (5题)
INSERT INTO questions (passage_id, part_id, question_number, question_text, question_type_id, score) VALUES
(18, 30, 41, '', 5, 2),
(18, 30, 42, '', 5, 2),
(18, 30, 43, '', 5, 2),
(18, 30, 44, '', 5, 2),
(18, 30, 45, '', 5, 2)
RETURNING id;

--
-- 假设返回 question_id: 237-241

-- 4. question_options (所有题目共用7个选项)
INSERT INTO question_options (question_id, option_label, option_text, is_correct) VALUES
(237, 'A', 'Students who stand out in a specific extracurricular activity will be favored by top-tier institutions.', FALSE),
(237, 'B', 'Students whose extracurricular activity has benefited their community are likely to win a scholarship.', FALSE),
(237, 'C', 'Undertaking too many extracurricular activities will hardly be seen as a plus by colleges.', TRUE),
(237, 'D', 'Student who exhibits activity in doing business can impress colleges.', FALSE),
(237, 'E', 'High school students participating in popular activity should excel in it.', FALSE),
(237, 'F', 'Engaging in uncommon activity can demonstrate Students'' determination and dedication.', FALSE),
(237, 'G', 'It is advisable for students to choose an extracurricular activity that is related to their future study at college.', FALSE);

INSERT INTO question_options (question_id, option_label, option_text, is_correct) VALUES
(238, 'A', 'Students who stand out in a specific extracurricular activity will be favored by top-tier institutions.', FALSE),
(238, 'B', 'Students whose extracurricular activity has benefited their community are likely to win a scholarship.', FALSE),
(238, 'C', 'Undertaking too many extracurricular activities will hardly be seen as a plus by colleges.', FALSE),
(238, 'D', 'Student who exhibits activity in doing business can impress colleges.', FALSE),
(238, 'E', 'High school students participating in popular activity should excel in it.', TRUE),
(238, 'F', 'Engaging in uncommon activity can demonstrate Students'' determination and dedication.', FALSE),
(238, 'G', 'It is advisable for students to choose an extracurricular activity that is related to their future study at college.', FALSE);

INSERT INTO question_options (question_id, option_label, option_text, is_correct) VALUES
(239, 'A', 'Students who stand out in a specific extracurricular activity will be favored by top-tier institutions.', TRUE),
(239, 'B', 'Students whose extracurricular activity has benefited their community are likely to win a scholarship.', FALSE),
(239, 'C', 'Undertaking too many extracurricular activities will hardly be seen as a plus by colleges.', FALSE),
(239, 'D', 'Student who exhibits activity in doing business can impress colleges.', FALSE),
(239, 'E', 'High school students participating in popular activity should excel in it.', FALSE),
(239, 'F', 'Engaging in uncommon activity can demonstrate Students'' determination and dedication.', FALSE),
(239, 'G', 'It is advisable for students to choose an extracurricular activity that is related to their future study at college.', FALSE);

INSERT INTO question_options (question_id, option_label, option_text, is_correct) VALUES
(240, 'A', 'Students who stand out in a specific extracurricular activity will be favored by top-tier institutions.', FALSE),
(240, 'B', 'Students whose extracurricular activity has benefited their community are likely to win a scholarship.', FALSE),
(240, 'C', 'Undertaking too many extracurricular activities will hardly be seen as a plus by colleges.', FALSE),
(240, 'D', 'Student who exhibits activity in doing business can impress colleges.', FALSE),
(240, 'E', 'High school students participating in popular activity should excel in it.', FALSE),
(240, 'F', 'Engaging in uncommon activity can demonstrate Students'' determination and dedication.', FALSE),
(240, 'G', 'It is advisable for students to choose an extracurricular activity that is related to their future study at college.', TRUE);

INSERT INTO question_options (question_id, option_label, option_text, is_correct) VALUES
(241, 'A', 'Students who stand out in a specific extracurricular activity will be favored by top-tier institutions.', FALSE),
(241, 'B', 'Students whose extracurricular activity has benefited their community are likely to win a scholarship.', TRUE),
(241, 'C', 'Undertaking too many extracurricular activities will hardly be seen as a plus by colleges.', FALSE),
(241, 'D', 'Student who exhibits activity in doing business can impress colleges.', FALSE),
(241, 'E', 'High school students participating in popular activity should excel in it.', FALSE),
(241, 'F', 'Engaging in uncommon activity can demonstrate Students'' determination and dedication.', FALSE),
(241, 'G', 'It is advisable for students to choose an extracurricular activity that is related to their future study at college.', FALSE);