# TweetArchiver
Archive user's tweets as screenshots and CSV using *Selenium*, no API access required.

## Requirements
Install requirements:
```bash
pip install -r requirements.txt
```

## Usage
Archive all tweets:
```bash
python app.py POTUS
```

Archive tweets from `date_start` until today:
```
python app.py POTUS 2022-01-01
```

Archive tweets from `date_start` until `date_end`:
```bash
python app.py POTUS 2022-01-01 2022-01-03
```

## Docker
```bash
docker build -t tweetarchiver .
docker run -t -v $PWD/data:/app/data tweetarchiver POTUS
```
