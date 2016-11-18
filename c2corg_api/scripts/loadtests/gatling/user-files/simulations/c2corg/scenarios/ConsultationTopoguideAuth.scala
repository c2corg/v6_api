package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._

class ConsultationTopoguideAuth extends Simulation {

        val httpProtocol = http
                .baseURL(C2corgConf.ui_url)
                .inferHtmlResources(C2corgConf.black_list, WhiteList())
                .acceptHeader("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
                .acceptEncodingHeader("gzip, deflate")
                .acceptLanguageHeader("fr-CH,en-US;q=0.7,en;q=0.3")
                .userAgentHeader("Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:49.0) Gecko/20100101 Firefox/49.0")

        val scn = scenario("ConsultationTopoguideAuth")
                .exec(Homepage.init)
                .pause(1)
                .exec(Auth.login)
                .pause(10)
                .exec(Homepage.initAuth)
                .pause(8)
                .exec(Homepage.browseAuth)
                .pause(4)
                .exec(Outing.view)
                .pause(9)
                .exec(Route.view)
                .pause(10)
                .exec(Image.upload)
                .pause(5)
                .exec(Outing.add)

        setUp(scn.inject(rampUsers(C2corgConf.num_users) over (C2corgConf.ramp_time_seconds seconds))).protocols(httpProtocol)
}
