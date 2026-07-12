DROP TABLE IF EXISTS venue_area, authorship, publication, area, person, venue CASCADE;

CREATE TABLE person (
    person_id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE venue (
    venue_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    venue_kind TEXT NOT NULL CHECK (venue_kind IN ('conference', 'journal'))
);

CREATE TABLE publication (
    publication_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    year INTEGER NOT NULL CHECK (year BETWEEN 1900 AND 2100),
    venue_id TEXT NOT NULL REFERENCES venue(venue_id)
);

CREATE TABLE authorship (
    publication_id TEXT NOT NULL REFERENCES publication(publication_id),
    person_id TEXT NOT NULL REFERENCES person(person_id),
    author_position INTEGER CHECK (author_position > 0),
    PRIMARY KEY (publication_id, person_id)
);

CREATE TABLE area (
    area_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    parent_area_id TEXT REFERENCES area(area_id)
);

CREATE TABLE venue_area (
    venue_id TEXT NOT NULL REFERENCES venue(venue_id),
    area_id TEXT NOT NULL REFERENCES area(area_id),
    PRIMARY KEY (venue_id, area_id)
);

CREATE INDEX authorship_person_idx ON authorship(person_id);
CREATE INDEX publication_venue_year_idx ON publication(venue_id, year);
CREATE INDEX area_parent_idx ON area(parent_area_id);
