INSERT INTO boat_class (name, length, width, foiling)
VALUES
  ('Waszp', 3.35, 2.25, TRUE),
  ('SuMoth', 4.36, 2.25, TRUE);

INSERT INTO boat (name, class_id, sailnumber)
VALUES
  (
    'SAGA',
    (SELECT id FROM boat_class WHERE name = 'SuMoth' LIMIT 1),
    'SWE 1'
  );
