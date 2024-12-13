term="fa2024"
mp="project"
files=(newdomain.py)

# get a username and password
echo -n "Username: "
read username

echo -n "Password: "
read -s password
echo

bundle=$(echo -n $username:$password | base64)

for f in "${files[@]}"
do
    echo 'sending' $f
    curl -s "https://courses.grainger.illinois.edu/cs340/fa2024/secure/put.php?f=${username}/${mp}/${f}" \
        -u "$username:$password" --ntlm \
        -X POST --data-binary "@${f}" \
        -H 'Content-Type: text/x-python' | \
        jq '{"'"${mp}/${f}"' size": .["'"${mp}/${f}"'"].len}'
done
